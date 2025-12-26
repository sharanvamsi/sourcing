import sqlite3
import json
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from security_manager import encrypt_key, decrypt_key

DB_NAME = "sourcing.db"
DATABASE_URL = os.getenv("DATABASE_URL") # Provided by cloud providers (Render, Railway, etc.)

def get_db_connection():
    if DATABASE_URL:
        # PostgreSQL (Cloud)
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn
    else:
        # SQLite (Local)
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Initializes the database schema with Postgres-safe syntax."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Teams
    if DATABASE_URL:
        cursor.execute("CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY)")
    else:
        cursor.execute("CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY)")
    
    # 2. Users (Fix Boolean Default)
    bool_default = "FALSE" if DATABASE_URL else "0"
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            team_name TEXT,
            password_hash TEXT,
            is_admin BOOLEAN DEFAULT {bool_default}
        )
    ''')
    
    # 3. User Keys
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_keys (
            user_email TEXT PRIMARY KEY,
            mixed_people_key_enc TEXT,
            bulk_match_key_enc TEXT,
            org_search_key_enc TEXT,
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
    ''')
    
    # 4. Baskets (Fix Serial Syntax)
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS baskets (
                id SERIAL PRIMARY KEY,
                user_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS baskets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # 5. Leads (Fix Boolean Default)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS leads (
            apollo_id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            title TEXT,
            organization_name TEXT,
            email TEXT,
            is_enriched BOOLEAN DEFAULT {bool_default},
            apollo_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 6. Basket Leads
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS basket_leads (
            basket_id INTEGER,
            lead_id TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (basket_id, lead_id)
        )
    ''')
    
    # 7. Credit Logs (Fix Serial Syntax)
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credit_logs (
                id SERIAL PRIMARY KEY,
                user_email TEXT,
                action TEXT,
                credit_spent INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                action TEXT,
                credit_spent INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # 8. Audit Logs (NEW for Sprint 7)
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                user_email TEXT,
                event_type TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                event_type TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    if not DATABASE_URL: conn.commit()
    conn.close()

def log_audit_event(email, event_type, details=None):
    """Logs a security or business event to the audit_logs table."""
    query("INSERT INTO audit_logs (user_email, event_type, details) VALUES (?, ?, ?)", 
          (email, event_type, details))

# --- KEY PERSISTENCE (ENCRYPTED) ---

def save_user_keys(email, keys_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_keys (user_email, mixed_people_key_enc, bulk_match_key_enc, org_search_key_enc)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_email) DO UPDATE SET
            mixed_people_key_enc = EXCLUDED.mixed_people_key_enc,
            bulk_match_key_enc = EXCLUDED.bulk_match_key_enc,
            org_search_key_enc = EXCLUDED.org_search_key_enc
    '''.replace("%s", "?") if not DATABASE_URL else '''
        INSERT INTO user_keys (user_email, mixed_people_key_enc, bulk_match_key_enc, org_search_key_enc)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_email) DO UPDATE SET
            mixed_people_key_enc = EXCLUDED.mixed_people_key_enc,
            bulk_match_key_enc = EXCLUDED.bulk_match_key_enc,
            org_search_key_enc = EXCLUDED.org_search_key_enc
    ''', (
        email,
        encrypt_key(keys_dict.get("MIXED_PEOPLE_API_KEY")),
        encrypt_key(keys_dict.get("BULK_MATCH_API_KEY")),
        encrypt_key(keys_dict.get("ORG_SEARCH_API_KEY"))
    ))
    if not DATABASE_URL: conn.commit()
    conn.close()

def get_user_keys(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_keys WHERE user_email = ?", (email,) if not DATABASE_URL else (email,))
    row = cursor.fetchone()
    conn.close()
    if not row: return None
    
    # In SQLite row is a Row object, in Postgres it's a dict (due to RealDictCursor)
    r = dict(row)
    return {
        "MIXED_PEOPLE_API_KEY": decrypt_key(r.get("mixed_people_key_enc")),
        "BULK_MATCH_API_KEY": decrypt_key(r.get("bulk_match_key_enc")),
        "ORG_SEARCH_API_KEY": decrypt_key(r.get("org_search_key_enc"))
    }


# --- REST OF THE LOGIC (WITH PARAM STYLE FIX) ---

def query(q, params=()):
    """Helper to handle Postgres vs SQLite parameter styles."""
    p_style = q.replace("?", "%s") if DATABASE_URL else q
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(p_style, params)
    if q.strip().upper().startswith("SELECT"):
        res = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return res
    else:
        if not DATABASE_URL: conn.commit()
        last_id = cursor.lastrowid if not DATABASE_URL else None
        conn.close()
        return last_id

def sync_roster(roster_data):
    for entry in roster_data:
        query("INSERT INTO teams (name) VALUES (?) ON CONFLICT DO NOTHING", (entry['team_name'],))
        query('''
            INSERT INTO users (email, name, team_name) VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET name=EXCLUDED.name, team_name=EXCLUDED.team_name
        ''', (entry['email'], entry['name'], entry['team_name']))

def get_basket_leads(user_email):
    rows = query("SELECT id FROM baskets WHERE user_email = ?", (user_email,))
    if not rows:
        basket_id = query("INSERT INTO baskets (user_email) VALUES (?)", (user_email,))
    else:
        basket_id = rows[0]['id']
        
    leads_rows = query('''
        SELECT l.* FROM leads l
        JOIN basket_leads bl ON l.apollo_id = bl.lead_id
        WHERE bl.basket_id = ?
    ''', (basket_id,))
    
    results = []
    for r in leads_rows:
        lead = dict(r)
        if lead['apollo_data']: lead.update(json.loads(lead['apollo_data']))
        results.append(lead)
    return results

def add_lead_to_basket(user_email, apollo_person):
    apollo_id = apollo_person.get('id')
    query('''
        INSERT INTO leads (apollo_id, first_name, last_name, title, organization_name, apollo_data)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(apollo_id) DO UPDATE SET apollo_data=EXCLUDED.apollo_data
    ''', (
        apollo_id, apollo_person.get('first_name'), apollo_person.get('last_name_obfuscated'),
        apollo_person.get('title'), apollo_person.get('organization', {}).get('name'), json.dumps(apollo_person)
    ))
    
    rows = query("SELECT id FROM baskets WHERE user_email = ?", (user_email,))
    basket_id = rows[0]['id'] if rows else query("INSERT INTO baskets (user_email) VALUES (?)", (user_email,))
    query("INSERT INTO basket_leads (basket_id, lead_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (basket_id, apollo_id))

def clear_basket(user_email):
    rows = query("SELECT id FROM baskets WHERE user_email = ?", (user_email,))
    if rows: query("DELETE FROM basket_leads WHERE basket_id = ?", (rows[0]['id'],))

def update_lead_enrichment(apollo_id, enriched_data):
    query('''
        UPDATE leads SET email = ?, first_name = ?, last_name = ?, is_enriched = 1, apollo_data = ?
        WHERE apollo_id = ?
    ''', (enriched_data.get('email'), enriched_data.get('first_name'), enriched_data.get('last_name'), json.dumps(enriched_data), apollo_id))

def log_credit_usage(user_email, action, credits):
    query("INSERT INTO credit_logs (user_email, action, credit_spent) VALUES (?, ?, ?)", (user_email, action, credits))

def is_lead_sourced_by_team(apollo_id, team_name):
    rows = query('''
        SELECT u.name FROM basket_leads bl
        JOIN baskets b ON bl.basket_id = b.id
        JOIN users u ON b.user_email = u.email
        WHERE bl.lead_id = ? AND u.team_name = ?
    ''', (apollo_id, team_name))
    return rows[0]['name'] if rows else None
