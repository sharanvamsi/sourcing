import sqlite3
import json
import os
from datetime import datetime
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
from security_manager import encrypt_key, decrypt_key
import sentry_sdk

def convert_datetime_to_str(obj):
    """
    Recursively converts datetime objects to ISO format strings in dictionaries and lists.
    This prevents JSON serialization errors when PostgreSQL returns TIMESTAMP as datetime objects.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: convert_datetime_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetime_to_str(item) for item in obj]
    else:
        return obj

DB_NAME = "sourcing.db"
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DATABASE CONNECTION POOLING ---
# We use ThreadedConnectionPool for multi-threaded Streamlit apps
db_pool = None
if DATABASE_URL:
    try:
        # Min 1, Max 20 connections
        db_pool = psycopg2.pool.ThreadedConnectionPool(1, 35, dsn=DATABASE_URL)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"❌ Critical: Could not initialize DB Pool: {e}")

def get_db_connection():
    """Gets a connection from the pool (Postgres) or local file (SQLite)."""
    if db_pool:
        # Return a connection from the pool
        conn = db_pool.getconn()
        # Set cursor factory globally for the session
        # (Note: RealDictCursor needs to be applied to the cursor)
        return conn
    elif not DATABASE_URL:
        # SQLite (Local Development)
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn
    else:
        raise RuntimeError("Database not configured. Set DATABASE_URL or run locally.")

def release_db_connection(conn):
    """Releases a connection back to the pool or closes it."""
    if db_pool:
        db_pool.putconn(conn)
    else:
        conn.close()

def check_environment():
    """Startup check for required environment variables."""
    missing = []
    if not os.getenv("MASTER_ENCRYPTION_SECRET"):
        missing.append("MASTER_ENCRYPTION_SECRET")
    
    if missing:
        err_msg = f"❌ Missing required Environment Variables: {', '.join(missing)}"
        print(err_msg)
        sentry_sdk.capture_message(err_msg, level="fatal")
        # In a real production app, we might exit(1) here
    
    return len(missing) == 0

def migrate_user_keys_schema():
    """Migrates user_keys table from 3-key schema to single-key schema."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if old columns exist
        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='user_keys' AND column_name='mixed_people_key_enc'
            """)
            has_old_schema = cursor.fetchone() is not None
        else:
            # SQLite check
            cursor.execute("PRAGMA table_info(user_keys)")
            columns = [row[1] for row in cursor.fetchall()]
            has_old_schema = 'mixed_people_key_enc' in columns
        
        if has_old_schema:
            # Migrate: Use the first available key (prefer MIXED_PEOPLE as it's most commonly used)
            if DATABASE_URL:
                # First ensure new column exists
                try:
                    cursor.execute("ALTER TABLE user_keys ADD COLUMN IF NOT EXISTS apollo_api_key_enc TEXT")
                except:
                    pass  # Column might already exist
                
                cursor.execute("""
                    UPDATE user_keys 
                    SET apollo_api_key_enc = COALESCE(mixed_people_key_enc, bulk_match_key_enc, org_search_key_enc)
                    WHERE apollo_api_key_enc IS NULL
                """)
                cursor.execute("""
                    ALTER TABLE user_keys 
                    DROP COLUMN IF EXISTS mixed_people_key_enc,
                    DROP COLUMN IF EXISTS bulk_match_key_enc,
                    DROP COLUMN IF EXISTS org_search_key_enc
                """)
                conn.commit()
            else:
                # SQLite doesn't support DROP COLUMN easily, so we'll recreate the table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_keys_new (
                        user_email TEXT PRIMARY KEY,
                        apollo_api_key_enc TEXT,
                        FOREIGN KEY (user_email) REFERENCES users (email)
                    )
                """)
                cursor.execute("""
                    INSERT INTO user_keys_new (user_email, apollo_api_key_enc)
                    SELECT user_email, COALESCE(mixed_people_key_enc, bulk_match_key_enc, org_search_key_enc)
                    FROM user_keys
                """)
                cursor.execute("DROP TABLE user_keys")
                cursor.execute("ALTER TABLE user_keys_new RENAME TO user_keys")
                conn.commit()
            
            print("✅ Migrated user_keys table to single-key schema")
        
        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

def migrate_users_schema():
    """Migrates users table to add is_admin column if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if is_admin column exists
        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='is_admin'
            """)
            has_is_admin = cursor.fetchone() is not None
        else:
            # SQLite check
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            has_is_admin = 'is_admin' in columns
        
        if not has_is_admin:
            # Add is_admin column
            if DATABASE_URL:
                cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
            else:
                # SQLite: Add column with default value
                cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added is_admin column to users table")
        
        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

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
            apollo_api_key_enc TEXT,
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

    # 8. Audit Logs
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

    # 9. Blacklist (NEW for Sprint 8)
    cursor.execute("CREATE TABLE IF NOT EXISTS blacklist (domain TEXT PRIMARY KEY)")

    # 10. Domain Cache (NEW for Sprint 8)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_cache (
            company_name TEXT PRIMARY KEY,
            domain TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    if DATABASE_URL:
        try:
            conn.commit()
        except Exception as commit_error:
            conn.rollback()
            raise commit_error
    else:
        conn.commit()
    release_db_connection(conn)
    
    # Run migrations for schema updates
    migrate_users_schema()  # Add is_admin column if missing
    migrate_user_keys_schema()  # Migrate user_keys to single-key schema

def log_audit_event(email, event_type, details=None):
    """Logs a security or business event to the audit_logs table and Sentry."""
    query("INSERT INTO audit_logs (user_email, event_type, details) VALUES (?, ?, ?)", 
          (email, event_type, details))
    
    # Also send to Sentry for external visibility (Audit Portability)
    if "LOGIN" in event_type:
        with sentry_sdk.configure_scope() as scope:
            scope.set_user({"email": email})
            scope.set_context("audit_event", {
                "event_type": event_type,
                "details": details
            })
            sentry_sdk.capture_message(f"Audit Event: {event_type} - {email}", level="info")

def get_all_users():
    """Retrieves all users from the database."""
    return query("SELECT email, name, team_name, is_admin FROM users ORDER BY name")

def get_user(email):
    """Retrieves a single user by email."""
    res = query("SELECT email, name, team_name, is_admin FROM users WHERE email = ?", (email.lower().strip(),))
    return res[0] if res else None
def add_user(email, name, team_name, is_admin=False):
    """Adds or updates a user in the database roster."""
    query('''
        INSERT INTO users (email, name, team_name, is_admin)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET 
            name=EXCLUDED.name, 
            team_name=EXCLUDED.team_name, 
            is_admin=EXCLUDED.is_admin
    ''', (email, name, team_name, bool(is_admin)))
    log_audit_event(email, "USER_ROSTER_UPDATED", f"User {name} added/updated via DB")

def migrate_roster_to_db(roster_data):
    """Migrates users from roster.json into the DB Users table."""
    users_in_db = get_all_users()
    if not users_in_db and roster_data:
        for entry in roster_data:
            is_admin_user = entry.get('is_admin', False)
            add_user(entry['email'], entry['name'], entry['team_name'], is_admin=is_admin_user)
        return True
    return False

# --- BLACKLIST & DOMAIN CACHE (NEW for Sprint 8) ---

def get_blacklist():
    """Retrieves all blacklisted domains."""
    res = query("SELECT domain FROM blacklist")
    return [r['domain'] for r in res]

def add_to_blacklist(domain):
    """Adds a domain to the blacklist."""
    query("INSERT INTO blacklist (domain) VALUES (?) ON CONFLICT DO NOTHING", (domain.lower().strip(),))

def remove_from_blacklist(domain):
    """Removes a domain from the blacklist."""
    query("DELETE FROM blacklist WHERE domain = ?", (domain.lower().strip(),))

def get_cached_domain(company_name):
    """Retrieves a cached domain for a company name."""
    res = query("SELECT domain FROM domain_cache WHERE company_name = ?", (company_name.lower().strip(),))
    return res[0]['domain'] if res else None

def update_domain_cache(company_name, domain):
    """Updates or adds a company domain to the cache."""
    query('''
        INSERT INTO domain_cache (company_name, domain)
        VALUES (?, ?)
        ON CONFLICT(company_name) DO UPDATE SET domain=EXCLUDED.domain, timestamp=CURRENT_TIMESTAMP
    ''', (company_name.lower().strip(), domain.lower().strip()))

# --- KEY PERSISTENCE (ENCRYPTED) ---

def save_user_keys(email, api_key):
    """Saves encrypted API key for a user using the safe query helper."""
    query('''
        INSERT INTO user_keys (user_email, apollo_api_key_enc)
        VALUES (?, ?)
        ON CONFLICT (user_email) DO UPDATE SET
            apollo_api_key_enc = EXCLUDED.apollo_api_key_enc
    ''', (
        email,
        encrypt_key(api_key)
    ))

def get_user_keys(email):
    """Retrieves and decrypts API key for a user using the safe query helper."""
    rows = query("SELECT * FROM user_keys WHERE user_email = ?", (email,))
    if not rows: 
        return None
    
    r = rows[0]
    api_key = decrypt_key(r.get("apollo_api_key_enc"))
    
    # Check if decryption failed
    if not api_key:
        sentry_sdk.capture_message(f"Failed to decrypt API key for user {email}", level="warning")
        return None
    
    return api_key

def delete_user_keys(email):
    """Deletes API key for a user from the database."""
    query("DELETE FROM user_keys WHERE user_email = ?", (email,))


# --- REST OF THE LOGIC (WITH PARAM STYLE FIX) ---

def query(q, params=()):
    """Helper to handle Postgres vs SQLite parameter styles with professional error handling."""
    p_style = q.replace("?", "%s") if DATABASE_URL else q
    conn = get_db_connection()
    try:
        # For Postgres, we use RealDictCursor to get dict results
        cursor_kwargs = {"cursor_factory": RealDictCursor} if DATABASE_URL else {}
        cursor = conn.cursor(**cursor_kwargs)
        
        cursor.execute(p_style, params)
        if q.strip().upper().startswith("SELECT"):
            # Fetch results
            rows = cursor.fetchall()
            # Convert SQLite rows to dict if necessary (Postgres already does this via factory)
            res = [dict(r) for r in rows] if not DATABASE_URL else rows
            release_db_connection(conn)
            return res
        else:
            if DATABASE_URL:
                # PostgreSQL: Explicit commit for write operations
                try:
                    conn.commit()
                except Exception as commit_error:
                    conn.rollback()
                    raise commit_error
            else:
                # SQLite needs commit
                conn.commit()
            last_id = cursor.lastrowid if not DATABASE_URL else None
            release_db_connection(conn)
            return last_id
    except Exception as e:
        if conn:
            try:
                if DATABASE_URL:
                    conn.rollback()
            except Exception:
                pass  # Ignore rollback errors
            release_db_connection(conn)
        # Log to Sentry for the developer
        sentry_sdk.capture_exception(e)
        # Re-raise with a polished message for the user
        raise RuntimeError(f"Database operation failed. The error has been logged.")

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
        # Convert datetime objects to strings before processing
        lead = convert_datetime_to_str(lead)
        if lead.get('apollo_data'): 
            try:
                lead.update(json.loads(lead['apollo_data']))
            except (json.JSONDecodeError, TypeError) as e:
                # Log error but continue processing other leads
                sentry_sdk.capture_exception(e)
                print(f"Warning: Failed to parse apollo_data for lead {lead.get('apollo_id')}: {e}")
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
        apollo_person.get('title'), apollo_person.get('organization', {}).get('name'), json.dumps(apollo_person, default=str)
    ))
    
    rows = query("SELECT id FROM baskets WHERE user_email = ?", (user_email,))
    basket_id = rows[0]['id'] if rows else query("INSERT INTO baskets (user_email) VALUES (?)", (user_email,))
    query("INSERT INTO basket_leads (basket_id, lead_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (basket_id, apollo_id))

def clear_basket(user_email):
    rows = query("SELECT id FROM baskets WHERE user_email = ?", (user_email,))
    if rows: query("DELETE FROM basket_leads WHERE basket_id = ?", (rows[0]['id'],))

def update_lead_enrichment(apollo_id, enriched_data):
    if not apollo_id:
        raise ValueError("apollo_id is required for update_lead_enrichment")
    is_enriched_val = True if DATABASE_URL else 1
    # Convert datetime objects to strings before JSON serialization
    serializable_data = convert_datetime_to_str(enriched_data)
    query('''
        UPDATE leads SET email = ?, first_name = ?, last_name = ?, is_enriched = ?, apollo_data = ?
        WHERE apollo_id = ?
    ''', (serializable_data.get('email'), serializable_data.get('first_name'), serializable_data.get('last_name'), is_enriched_val, json.dumps(serializable_data), apollo_id))

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
