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

# Allowed teams - only these teams are valid
# "External" is used as an internal placeholder for non-ABA users.
ALLOWED_TEAMS = ["BD", "Finance", "Marketing", "Strategy", "NPO", "Exec Board", "External"]

# Team credit limit (Exec Board team has no limit)
TEAM_CREDIT_LIMIT = 4500
EXEC_TEAM_NAME = "Exec Board"
EXTERNAL_TEAM_NAME = "External"

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

def migrate_team_requirement():
    """Migrates users table to enforce team_name NOT NULL and add foreign key constraint."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if team_name is nullable
        if DATABASE_URL:
            cursor.execute("""
                SELECT is_nullable 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='team_name'
            """)
            result = cursor.fetchone()
            is_nullable = result and result[0] == 'YES'
        else:
            # SQLite check
            cursor.execute("PRAGMA table_info(users)")
            columns = cursor.fetchall()
            is_nullable = True
            for col in columns:
                if col[1] == 'team_name':
                    is_nullable = col[3] == 0  # 0 means nullable in SQLite
                    break
        
        if is_nullable:
            # For PostgreSQL, we can alter the column
            if DATABASE_URL:
                # First, ensure all users have a team (should already be the case per user's statement)
                # But defensive check: assign NULL teams to a default (shouldn't happen)
                cursor.execute("SELECT COUNT(*) FROM users WHERE team_name IS NULL OR team_name = ''")
                null_count = cursor.fetchone()[0]
                if null_count > 0:
                    print(f"⚠️  Found {null_count} users without teams. This shouldn't happen per requirements.")
                    # We'll let the constraint fail if there are NULL teams
                
                # Add NOT NULL constraint
                try:
                    cursor.execute("ALTER TABLE users ALTER COLUMN team_name SET NOT NULL")
                    conn.commit()
                    print("✅ Added NOT NULL constraint to team_name")
                except Exception as e:
                    conn.rollback()
                    print(f"⚠️  Could not add NOT NULL constraint: {e}")
                    raise
                
                # Add foreign key constraint
                try:
                    cursor.execute("""
                        ALTER TABLE users 
                        ADD CONSTRAINT fk_users_team 
                        FOREIGN KEY (team_name) REFERENCES teams(name)
                    """)
                    conn.commit()
                    print("✅ Added foreign key constraint for team_name")
                except Exception as e:
                    # Constraint might already exist
                    if "already exists" not in str(e).lower():
                        conn.rollback()
                        print(f"⚠️  Could not add foreign key constraint: {e}")
            else:
                # SQLite: Need to recreate table
                print("🔄 Migrating users table for SQLite (adding NOT NULL and foreign key)...")
                
                # Create new table with constraints
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users_new (
                        email TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        team_name TEXT NOT NULL,
                        password_hash TEXT,
                        is_admin INTEGER DEFAULT 0,
                        FOREIGN KEY (team_name) REFERENCES teams(name)
                    )
                """)
                
                # Copy data
                cursor.execute("""
                    INSERT INTO users_new (email, name, team_name, password_hash, is_admin)
                    SELECT email, name, team_name, password_hash, is_admin
                    FROM users
                    WHERE team_name IS NOT NULL AND team_name != ''
                """)
                
                # Drop old table and rename
                cursor.execute("DROP TABLE users")
                cursor.execute("ALTER TABLE users_new RENAME TO users")
                conn.commit()
                print("✅ Migrated users table with NOT NULL and foreign key constraints")
        
        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

def migrate_user_credits_column():
    """Migrates users table to add total_credits_used column if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if total_credits_used column exists
        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='total_credits_used'
            """)
            has_column = cursor.fetchone() is not None
        else:
            # SQLite check
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            has_column = 'total_credits_used' in columns
        
        if not has_column:
            # Add total_credits_used column
            if DATABASE_URL:
                cursor.execute("ALTER TABLE users ADD COLUMN total_credits_used INTEGER DEFAULT 0")
            else:
                # SQLite: Add column with default value
                cursor.execute("ALTER TABLE users ADD COLUMN total_credits_used INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added total_credits_used column to users table")
            
            # Calculate initial totals for existing users
            cursor.execute("""
                UPDATE users 
                SET total_credits_used = (
                    SELECT COALESCE(SUM(credit_spent), 0) 
                    FROM credit_logs 
                    WHERE credit_logs.user_email = users.email
                )
            """)
            conn.commit()
            print("✅ Calculated initial credit totals for existing users")
        
        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

def migrate_team_credits_column():
    """Migrates teams table to add total_credits_used column if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if total_credits_used column exists
        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='teams' AND column_name='total_credits_used'
            """)
            has_column = cursor.fetchone() is not None
        else:
            # SQLite check
            cursor.execute("PRAGMA table_info(teams)")
            columns = [row[1] for row in cursor.fetchall()]
            has_column = 'total_credits_used' in columns

        if not has_column:
            # Add total_credits_used column
            if DATABASE_URL:
                cursor.execute("ALTER TABLE teams ADD COLUMN total_credits_used INTEGER DEFAULT 0")
            else:
                # SQLite: Add column with default value
                cursor.execute("ALTER TABLE teams ADD COLUMN total_credits_used INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added total_credits_used column to teams table")

            # Calculate initial team totals by summing all team members' total_credits_used
            cursor.execute("""
                UPDATE teams
                SET total_credits_used = (
                    SELECT COALESCE(SUM(total_credits_used), 0)
                    FROM users
                    WHERE users.team_name = teams.name
                )
            """)
            conn.commit()
            print("✅ Calculated initial team credit totals from member totals")

        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

def migrate_user_role_column():
    """Migrates users table to add role column if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if role column exists
        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='users' AND column_name='role'
            """)
            has_column = cursor.fetchone() is not None
        else:
            # SQLite check
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            has_column = 'role' in columns

        if not has_column:
            # Add role column with default 'consultant'
            if DATABASE_URL:
                cursor.execute("""
                    ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'consultant'
                    CHECK (role IN ('consultant', 'pm'))
                """)
            else:
                # SQLite: Add column with default value (no CHECK constraint in SQLite ADD COLUMN)
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'consultant'")
            conn.commit()
            print("✅ Added role column to users table")

        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

def migrate_user_blacklist_exempt_column():
    """Migrates users table to add blacklist_exempt column if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='users' AND column_name='blacklist_exempt'
            """)
            has_column = cursor.fetchone() is not None
        else:
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            has_column = 'blacklist_exempt' in columns

        if not has_column:
            if DATABASE_URL:
                cursor.execute("ALTER TABLE users ADD COLUMN blacklist_exempt BOOLEAN DEFAULT FALSE")
            else:
                cursor.execute("ALTER TABLE users ADD COLUMN blacklist_exempt INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added blacklist_exempt column to users table")

        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

def migrate_user_membership_column():
    """Migrates users table to add membership column if it doesn't exist (aba vs external)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='users' AND column_name='membership'
            """)
            has_column = cursor.fetchone() is not None
        else:
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            has_column = 'membership' in columns

        if not has_column:
            # Default everyone to ABA to preserve existing behavior
            if DATABASE_URL:
                cursor.execute("ALTER TABLE users ADD COLUMN membership TEXT DEFAULT 'aba'")
            else:
                cursor.execute("ALTER TABLE users ADD COLUMN membership TEXT DEFAULT 'aba'")
            conn.commit()
            print("✅ Added membership column to users table")

        release_db_connection(conn)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"⚠️  Migration warning: {e}")

def migrate_user_keys_sendgrid():
    """Migrates user_keys table to add sendgrid_api_key_enc column if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if sendgrid_api_key_enc column exists
        if DATABASE_URL:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='user_keys' AND column_name='sendgrid_api_key_enc'
            """)
            has_column = cursor.fetchone() is not None
        else:
            # SQLite check
            cursor.execute("PRAGMA table_info(user_keys)")
            columns = [row[1] for row in cursor.fetchall()]
            has_column = 'sendgrid_api_key_enc' in columns

        if not has_column:
            # Add sendgrid_api_key_enc column
            if DATABASE_URL:
                cursor.execute("ALTER TABLE user_keys ADD COLUMN sendgrid_api_key_enc TEXT")
            else:
                cursor.execute("ALTER TABLE user_keys ADD COLUMN sendgrid_api_key_enc TEXT")
            conn.commit()
            print("✅ Added sendgrid_api_key_enc column to user_keys table")

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
        cursor.execute("CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY, total_credits_used INTEGER DEFAULT 0)")
    else:
        cursor.execute("CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY, total_credits_used INTEGER DEFAULT 0)")
    
    # Ensure all allowed teams exist
    for team in ALLOWED_TEAMS:
        # Use correct placeholder syntax for PostgreSQL vs SQLite
        sql = "INSERT INTO teams (name) VALUES (%s) ON CONFLICT DO NOTHING" if DATABASE_URL else "INSERT INTO teams (name) VALUES (?) ON CONFLICT DO NOTHING"
        cursor.execute(sql, (team,))
    
    # 2. Users (Fix Boolean Default) - team_name is NOT NULL with foreign key
    bool_default = "FALSE" if DATABASE_URL else "0"
    if DATABASE_URL:
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                team_name TEXT NOT NULL,
                password_hash TEXT,
                is_admin BOOLEAN DEFAULT {bool_default},
                blacklist_exempt BOOLEAN DEFAULT {bool_default},
                membership TEXT DEFAULT 'aba',
                total_credits_used INTEGER DEFAULT 0,
                FOREIGN KEY (team_name) REFERENCES teams(name)
            )
        ''')
    else:
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                team_name TEXT NOT NULL,
                password_hash TEXT,
                is_admin INTEGER DEFAULT {bool_default},
                blacklist_exempt INTEGER DEFAULT {bool_default},
                membership TEXT DEFAULT 'aba',
                total_credits_used INTEGER DEFAULT 0,
                FOREIGN KEY (team_name) REFERENCES teams(name)
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

    # 11. User Sessions (for persistent login)
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_token TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_email) REFERENCES users (email) ON DELETE CASCADE
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_token TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_email) REFERENCES users (email)
            )
        ''')

    # 12. Team Baskets (shared lead inventory per team)
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_baskets (
                id SERIAL PRIMARY KEY,
                team_name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_name) REFERENCES teams(name)
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_baskets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_name) REFERENCES teams(name)
            )
        ''')

    # 13. Team Basket Leads (enriched leads in team basket)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS team_basket_leads (
            team_basket_id INTEGER NOT NULL,
            lead_id TEXT NOT NULL,
            added_by TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_contacted BOOLEAN DEFAULT {bool_default},
            contacted_by TEXT,
            contacted_at TIMESTAMP,
            PRIMARY KEY (team_basket_id, lead_id),
            FOREIGN KEY (team_basket_id) REFERENCES team_baskets(id),
            FOREIGN KEY (lead_id) REFERENCES leads(apollo_id),
            FOREIGN KEY (added_by) REFERENCES users(email)
        )
    ''')

    # 14. Email Templates
    if DATABASE_URL:
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS email_templates (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                body_html TEXT NOT NULL,
                body_text TEXT,
                created_by TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(email)
            )
        ''')
    else:
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS email_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                body_html TEXT NOT NULL,
                body_text TEXT,
                created_by TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(email)
            )
        ''')

    # 15. Email Campaigns
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_campaigns (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                team_name TEXT NOT NULL,
                template_id INTEGER,
                sender_email TEXT NOT NULL,
                sender_name TEXT,
                created_by TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                total_recipients INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_name) REFERENCES teams(name),
                FOREIGN KEY (template_id) REFERENCES email_templates(id),
                FOREIGN KEY (created_by) REFERENCES users(email)
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                team_name TEXT NOT NULL,
                template_id INTEGER,
                sender_email TEXT NOT NULL,
                sender_name TEXT,
                created_by TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                total_recipients INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_name) REFERENCES teams(name),
                FOREIGN KEY (template_id) REFERENCES email_templates(id),
                FOREIGN KEY (created_by) REFERENCES users(email)
            )
        ''')

    # 16. Sent Emails (individual email tracking)
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_emails (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER NOT NULL,
                lead_id TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                sendgrid_message_id TEXT,
                status TEXT DEFAULT 'pending',
                sent_at TIMESTAMP,
                opened_at TIMESTAMP,
                clicked_at TIMESTAMP,
                open_count INTEGER DEFAULT 0,
                click_count INTEGER DEFAULT 0,
                FOREIGN KEY (campaign_id) REFERENCES email_campaigns(id),
                FOREIGN KEY (lead_id) REFERENCES leads(apollo_id)
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                lead_id TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                sendgrid_message_id TEXT,
                status TEXT DEFAULT 'pending',
                sent_at TIMESTAMP,
                opened_at TIMESTAMP,
                clicked_at TIMESTAMP,
                open_count INTEGER DEFAULT 0,
                click_count INTEGER DEFAULT 0,
                FOREIGN KEY (campaign_id) REFERENCES email_campaigns(id),
                FOREIGN KEY (lead_id) REFERENCES leads(apollo_id)
            )
        ''')

    # 17. Email Events (webhook event tracking)
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_events (
                id SERIAL PRIMARY KEY,
                sent_email_id INTEGER,
                sendgrid_message_id TEXT,
                event_type TEXT NOT NULL,
                event_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sent_email_id) REFERENCES sent_emails(id)
            )
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_email_id INTEGER,
                sendgrid_message_id TEXT,
                event_type TEXT NOT NULL,
                event_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sent_email_id) REFERENCES sent_emails(id)
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
    migrate_team_requirement()  # Enforce team_name NOT NULL and foreign key
    migrate_user_credits_column()  # Add total_credits_used column and calculate initial totals
    migrate_team_credits_column()  # Add total_credits_used column to teams and calculate initial totals
    migrate_user_role_column()  # Add role column to users
    migrate_user_blacklist_exempt_column()  # Add blacklist_exempt column to users
    migrate_user_membership_column()  # Add membership column to users
    migrate_user_keys_sendgrid()  # Add sendgrid_api_key_enc column to user_keys

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
    return query("SELECT email, name, team_name, is_admin, role, blacklist_exempt, membership FROM users ORDER BY name")

def get_user(email):
    """Retrieves a single user by email."""
    res = query("SELECT email, name, team_name, is_admin, role, blacklist_exempt, membership FROM users WHERE email = ?", (email.lower().strip(),))
    return res[0] if res else None
def add_user(email, name, team_name, is_admin=False, role='consultant', blacklist_exempt=False, membership='aba'):
    """Adds or updates a user in the database roster."""
    # Validate role
    if role not in ('consultant', 'pm'):
        raise ValueError(f"role must be 'consultant' or 'pm'. Got: '{role}'")

    # Validate membership
    membership = (membership or 'aba').strip().lower()
    if membership not in ('aba', 'external'):
        raise ValueError("membership must be 'aba' or 'external'")

    # Team handling:
    # - ABA users must pick a valid team
    # - External users do not need a team; we store an internal placeholder
    if membership == "external":
        team_name = EXTERNAL_TEAM_NAME
    else:
        if not team_name or not team_name.strip():
            raise ValueError("team_name is required and cannot be empty")
        team_name = team_name.strip()
        if team_name not in ALLOWED_TEAMS:
            raise ValueError(f"team_name must be one of: {', '.join(ALLOWED_TEAMS)}. Got: '{team_name}'")

    # Ensure team exists in teams table (defensive check)
    query("INSERT INTO teams (name) VALUES (?) ON CONFLICT DO NOTHING", (team_name,))

    query('''
        INSERT INTO users (email, name, team_name, is_admin, role, blacklist_exempt, membership)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name=EXCLUDED.name,
            team_name=EXCLUDED.team_name,
            is_admin=EXCLUDED.is_admin,
            role=EXCLUDED.role,
            blacklist_exempt=EXCLUDED.blacklist_exempt,
            membership=EXCLUDED.membership
    ''', (email, name, team_name, bool(is_admin), role, bool(blacklist_exempt), membership))
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
        team_name = entry.get('team_name', '').strip()

        # Validate team_name is in allowed teams
        if not team_name or team_name not in ALLOWED_TEAMS:
            raise ValueError(f"Invalid team_name '{team_name}' for user {entry.get('email')}. Must be one of: {', '.join(ALLOWED_TEAMS)}")

        # Ensure team exists in teams table
        query("INSERT INTO teams (name) VALUES (?) ON CONFLICT DO NOTHING", (team_name,))

        # Use add_user for validation and proper handling
        is_admin = entry.get('is_admin', False)
        role = entry.get('role', 'consultant')
        add_user(entry['email'], entry['name'], team_name, is_admin=is_admin, role=role)

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

def get_lead_by_id(apollo_id):
    """Retrieves a lead by apollo_id. Returns None if not found."""
    if not apollo_id:
        return None
    rows = query("SELECT * FROM leads WHERE apollo_id = ?", (apollo_id,))
    if not rows:
        return None
    lead = dict(rows[0])
    # Convert datetime objects to strings
    lead = convert_datetime_to_str(lead)
    # Parse apollo_data if it exists
    if lead.get('apollo_data'):
        try:
            apollo_data = json.loads(lead['apollo_data'])
            # Merge apollo_data into lead dict
            lead.update(apollo_data)
        except (json.JSONDecodeError, TypeError) as e:
            sentry_sdk.capture_exception(e)
            print(f"Warning: Failed to parse apollo_data for lead {apollo_id}: {e}")
    return lead

def is_lead_enriched(apollo_id):
    """Checks if a lead exists in the database and is already enriched."""
    if not apollo_id:
        return False
    rows = query("SELECT is_enriched FROM leads WHERE apollo_id = ?", (apollo_id,))
    if not rows:
        return False
    # Check if enriched (handle both boolean and integer)
    is_enriched = rows[0].get('is_enriched')
    return bool(is_enriched) if is_enriched is not None else False

def store_enriched_lead(apollo_id, enriched_data):
    """
    Stores or updates a lead with complete enrichment data.
    Stores ALL enrichment API response data in apollo_data JSON field.
    """
    if not apollo_id:
        raise ValueError("apollo_id is required for store_enriched_lead")
    
    # Convert datetime objects to strings before JSON serialization
    serializable_data = convert_datetime_to_str(enriched_data)
    
    # Extract key fields for direct columns
    email = serializable_data.get('email')
    first_name = serializable_data.get('first_name')
    last_name = serializable_data.get('last_name')
    title = serializable_data.get('title')
    organization_name = None
    if serializable_data.get('organization'):
        organization_name = serializable_data.get('organization', {}).get('name')
    
    is_enriched_val = True if DATABASE_URL else 1
    
    # Store complete enrichment data in apollo_data JSON field
    query('''
        INSERT INTO leads (apollo_id, first_name, last_name, title, organization_name, email, is_enriched, apollo_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(apollo_id) DO UPDATE SET 
            email = EXCLUDED.email,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            title = EXCLUDED.title,
            organization_name = EXCLUDED.organization_name,
            is_enriched = EXCLUDED.is_enriched,
            apollo_data = EXCLUDED.apollo_data
    ''', (
        apollo_id,
        first_name,
        last_name,
        title,
        organization_name,
        email,
        is_enriched_val,
        json.dumps(serializable_data, default=str)
    ))

def update_lead_enrichment(apollo_id, enriched_data):
    """Updates an existing lead with enrichment data. Uses store_enriched_lead for consistency."""
    store_enriched_lead(apollo_id, enriched_data)

def log_credit_usage(user_email, action, credits):
    """Logs credit usage event and updates user's and team's total credits atomically."""
    # Insert individual credit event
    query("INSERT INTO credit_logs (user_email, action, credit_spent) VALUES (?, ?, ?)", (user_email, action, credits))
    
    # Get user's team_name
    user = get_user(user_email)
    if not user:
        raise ValueError(f"User {user_email} not found")
    
    team_name = user.get('team_name')
    if not team_name:
        raise ValueError(f"User {user_email} has no team_name")
    
    # Atomically update user's total credits
    query("UPDATE users SET total_credits_used = total_credits_used + ? WHERE email = ?", (credits, user_email))
    
    # Atomically update team's total credits
    query("UPDATE teams SET total_credits_used = total_credits_used + ? WHERE name = ?", (credits, team_name))

def get_user_credit_total(user_email):
    """Retrieves the pre-calculated total credits used by a user."""
    res = query("SELECT total_credits_used FROM users WHERE email = ?", (user_email,))
    if res and len(res) > 0:
        return res[0].get('total_credits_used', 0) or 0
    return 0

def get_team_credit_total(team_name):
    """Retrieves the pre-calculated total credits used by a team."""
    res = query("SELECT total_credits_used FROM teams WHERE name = ?", (team_name,))
    if res and len(res) > 0:
        return res[0].get('total_credits_used', 0) or 0
    return 0

def get_team_members(team_name):
    """Retrieves list of all users belonging to a team."""
    return query("SELECT email, name, team_name, is_admin, total_credits_used FROM users WHERE team_name = ? ORDER BY name", (team_name,))

def get_team_info(team_name):
    """Returns team info including members and credits."""
    team_credits = get_team_credit_total(team_name)
    members = get_team_members(team_name)
    return {
        'name': team_name,
        'total_credits_used': team_credits,
        'members': members,
        'member_count': len(members) if members else 0
    }

def create_user_session(user_email, expires_in_hours=24):
    """
    Creates a new session for a user.
    
    Args:
        user_email: User's email address
        expires_in_hours: Hours until session expires (default: 24)
        
    Returns:
        str: Session token
    """
    import secrets
    from datetime import timedelta
    
    # Generate secure random token
    session_token = secrets.token_urlsafe(32)
    
    # Calculate expiration time
    if DATABASE_URL:
        expires_at = datetime.now() + timedelta(hours=expires_in_hours)
    else:
        expires_at = datetime.now() + timedelta(hours=expires_in_hours)
    
    # Store session in database
    query('''
        INSERT INTO user_sessions (session_token, user_email, expires_at)
        VALUES (?, ?, ?)
    ''', (session_token, user_email, expires_at))
    
    return session_token


def get_user_from_session(session_token):
    """
    Retrieves user information from a session token.
    
    Args:
        session_token: Session token from URL query parameter
        
    Returns:
        dict: User object if session is valid, None otherwise
    """
    if not session_token:
        return None
    
    # Check if session exists and is not expired
    rows = query('''
        SELECT user_email, expires_at 
        FROM user_sessions 
        WHERE session_token = ? AND (expires_at IS NULL OR expires_at > ?)
    ''', (session_token, datetime.now()))
    
    if not rows:
        return None
    
    user_email = rows[0]['user_email']
    user = get_user(user_email)
    return user


def delete_user_session(session_token):
    """
    Deletes a user session (logout).
    
    Args:
        session_token: Session token to delete
    """
    if session_token:
        query("DELETE FROM user_sessions WHERE session_token = ?", (session_token,))


def cleanup_expired_sessions():
    """
    Removes expired sessions from the database.
    """
    query("DELETE FROM user_sessions WHERE expires_at IS NOT NULL AND expires_at < ?", (datetime.now(),))


def check_team_credit_limit(team_name, credits_to_add=0):
    """
    Checks if a team can perform an operation that would add credits.

    Args:
        team_name: Name of the team
        credits_to_add: Number of credits that would be added (default: 0, just checking current status)

    Returns:
        tuple: (is_allowed: bool, remaining_credits: int, current_credits: int)
    """
    # Exec Board + External have no limit
    if team_name in (EXEC_TEAM_NAME, EXTERNAL_TEAM_NAME):
        return (True, None, get_team_credit_total(team_name))

    # Get current team credits
    current_credits = get_team_credit_total(team_name)

    # Calculate total after adding credits
    total_after = current_credits + credits_to_add

    # Check if it would exceed limit
    if total_after > TEAM_CREDIT_LIMIT:
        remaining = max(0, TEAM_CREDIT_LIMIT - current_credits)
        return (False, remaining, current_credits)

    # Check if already at or over limit (for search blocking)
    if current_credits >= TEAM_CREDIT_LIMIT:
        return (False, 0, current_credits)

    # Within limit
    remaining = TEAM_CREDIT_LIMIT - total_after
    return (True, remaining, current_credits)


# --- TEAM BASKET FUNCTIONS ---

def get_or_create_team_basket(team_name):
    """Gets or creates a team basket for the given team."""
    rows = query("SELECT id FROM team_baskets WHERE team_name = ?", (team_name,))
    if rows:
        return rows[0]['id']
    # Create new team basket
    query("INSERT INTO team_baskets (team_name) VALUES (?)", (team_name,))
    rows = query("SELECT id FROM team_baskets WHERE team_name = ?", (team_name,))
    return rows[0]['id'] if rows else None

def get_team_basket_leads(team_name, filter_contacted=None):
    """
    Gets all leads in a team's basket.

    Args:
        team_name: Name of the team
        filter_contacted: None for all, True for contacted only, False for non-contacted only

    Returns:
        List of lead dictionaries with basket metadata
    """
    basket_id = get_or_create_team_basket(team_name)

    base_query = '''
        SELECT l.*, tbl.added_by, tbl.added_at, tbl.is_contacted, tbl.contacted_by, tbl.contacted_at
        FROM leads l
        JOIN team_basket_leads tbl ON l.apollo_id = tbl.lead_id
        WHERE tbl.team_basket_id = ?
    '''

    if filter_contacted is True:
        base_query += " AND tbl.is_contacted = " + ("TRUE" if DATABASE_URL else "1")
    elif filter_contacted is False:
        base_query += " AND (tbl.is_contacted = " + ("FALSE" if DATABASE_URL else "0") + " OR tbl.is_contacted IS NULL)"

    base_query += " ORDER BY tbl.added_at DESC"

    rows = query(base_query, (basket_id,))

    results = []
    for r in rows:
        lead = dict(r)
        lead = convert_datetime_to_str(lead)
        if lead.get('apollo_data'):
            try:
                lead.update(json.loads(lead['apollo_data']))
            except (json.JSONDecodeError, TypeError) as e:
                sentry_sdk.capture_exception(e)
        results.append(lead)
    return results

def is_lead_in_team_basket(team_name, apollo_id):
    """Checks if a lead is already in the team's basket."""
    basket_id = get_or_create_team_basket(team_name)
    rows = query(
        "SELECT 1 FROM team_basket_leads WHERE team_basket_id = ? AND lead_id = ?",
        (basket_id, apollo_id)
    )
    return len(rows) > 0

def check_team_basket_duplicates(team_name, leads):
    """
    Checks which leads are already in the team basket.

    Args:
        team_name: Name of the team
        leads: List of lead dictionaries with 'id' field

    Returns:
        tuple: (duplicates list, non_duplicates list)
    """
    basket_id = get_or_create_team_basket(team_name)
    duplicates = []
    non_duplicates = []

    for lead in leads:
        apollo_id = lead.get('id') or lead.get('apollo_id')
        if not apollo_id:
            non_duplicates.append(lead)
            continue

        rows = query(
            "SELECT 1 FROM team_basket_leads WHERE team_basket_id = ? AND lead_id = ?",
            (basket_id, apollo_id)
        )
        if rows:
            duplicates.append(lead)
        else:
            non_duplicates.append(lead)

    return duplicates, non_duplicates

def add_leads_to_team_basket(team_name, leads, added_by):
    """
    Adds enriched leads to the team basket.

    Args:
        team_name: Name of the team
        leads: List of enriched lead dictionaries
        added_by: Email of user who enriched the leads

    Returns:
        Number of leads added (excluding duplicates)
    """
    basket_id = get_or_create_team_basket(team_name)
    added_count = 0

    for lead in leads:
        apollo_id = lead.get('id') or lead.get('apollo_id')
        if not apollo_id:
            continue

        # Skip if already in basket
        if is_lead_in_team_basket(team_name, apollo_id):
            continue

        query('''
            INSERT INTO team_basket_leads (team_basket_id, lead_id, added_by)
            VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
        ''', (basket_id, apollo_id, added_by))
        added_count += 1

    return added_count

def mark_lead_contacted(team_name, lead_id, pm_email):
    """Marks a lead as contacted after PM sends email."""
    basket_id = get_or_create_team_basket(team_name)
    query('''
        UPDATE team_basket_leads
        SET is_contacted = ?, contacted_by = ?, contacted_at = ?
        WHERE team_basket_id = ? AND lead_id = ?
    ''', (True if DATABASE_URL else 1, pm_email, datetime.now(), basket_id, lead_id))

def get_team_basket_stats(team_name):
    """Gets statistics for a team's basket."""
    basket_id = get_or_create_team_basket(team_name)

    total = query(
        "SELECT COUNT(*) as count FROM team_basket_leads WHERE team_basket_id = ?",
        (basket_id,)
    )

    contacted_condition = "TRUE" if DATABASE_URL else "1"
    contacted = query(
        f"SELECT COUNT(*) as count FROM team_basket_leads WHERE team_basket_id = ? AND is_contacted = {contacted_condition}",
        (basket_id,)
    )

    total_count = total[0]['count'] if total else 0
    contacted_count = contacted[0]['count'] if contacted else 0

    return {
        'total': total_count,
        'contacted': contacted_count,
        'available': total_count - contacted_count
    }


# --- EMAIL TEMPLATE & CAMPAIGN FUNCTIONS ---

def get_email_templates(user_email=None, active_only=True):
    """Gets email templates, optionally filtered by creator."""
    base_query = "SELECT * FROM email_templates"
    conditions = []
    params = []

    if active_only:
        active_condition = "TRUE" if DATABASE_URL else "1"
        conditions.append(f"is_active = {active_condition}")

    if user_email:
        conditions.append("created_by = ?")
        params.append(user_email)

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    base_query += " ORDER BY created_at DESC"

    rows = query(base_query, tuple(params))
    return [convert_datetime_to_str(dict(r)) for r in rows]

def get_email_template(template_id):
    """Gets a single email template by ID."""
    rows = query("SELECT * FROM email_templates WHERE id = ?", (template_id,))
    if rows:
        return convert_datetime_to_str(dict(rows[0]))
    return None

def save_email_template(name, subject, body_html, body_text, created_by, template_id=None):
    """Creates or updates an email template."""
    if template_id:
        # Update existing
        query('''
            UPDATE email_templates
            SET name = ?, subject = ?, body_html = ?, body_text = ?
            WHERE id = ?
        ''', (name, subject, body_html, body_text, template_id))
        return template_id
    else:
        # Create new
        query('''
            INSERT INTO email_templates (name, subject, body_html, body_text, created_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, subject, body_html, body_text, created_by))
        # Get the newly created template ID
        rows = query(
            "SELECT id FROM email_templates WHERE name = ? AND created_by = ? ORDER BY created_at DESC LIMIT 1",
            (name, created_by)
        )
        return rows[0]['id'] if rows else None

def delete_email_template(template_id):
    """Soft deletes an email template by setting is_active to false."""
    inactive = "FALSE" if DATABASE_URL else "0"
    query(f"UPDATE email_templates SET is_active = {inactive} WHERE id = ?", (template_id,))

def create_campaign(name, team_name, template_id, sender_email, sender_name, created_by, lead_ids):
    """
    Creates a new email campaign.

    Args:
        name: Campaign name
        team_name: Team name
        template_id: Template ID to use
        sender_email: Sender email address
        sender_name: Sender display name
        created_by: PM email who created
        lead_ids: List of lead IDs to include

    Returns:
        Campaign ID
    """
    query('''
        INSERT INTO email_campaigns (name, team_name, template_id, sender_email, sender_name, created_by, total_recipients, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
    ''', (name, team_name, template_id, sender_email, sender_name, created_by, len(lead_ids)))

    # Get the campaign ID
    rows = query(
        "SELECT id FROM email_campaigns WHERE name = ? AND created_by = ? ORDER BY created_at DESC LIMIT 1",
        (name, created_by)
    )
    campaign_id = rows[0]['id'] if rows else None

    if campaign_id:
        # Create sent_emails records for each lead
        for lead_id in lead_ids:
            lead = get_lead_by_id(lead_id)
            if lead and lead.get('email'):
                query('''
                    INSERT INTO sent_emails (campaign_id, lead_id, recipient_email, status)
                    VALUES (?, ?, ?, 'pending')
                ''', (campaign_id, lead_id, lead['email']))

    return campaign_id

def get_campaign(campaign_id):
    """Gets a single campaign by ID."""
    rows = query("SELECT * FROM email_campaigns WHERE id = ?", (campaign_id,))
    if rows:
        return convert_datetime_to_str(dict(rows[0]))
    return None

def get_team_campaigns(team_name):
    """Gets all campaigns for a team."""
    rows = query(
        "SELECT * FROM email_campaigns WHERE team_name = ? ORDER BY created_at DESC",
        (team_name,)
    )
    return [convert_datetime_to_str(dict(r)) for r in rows]

def update_campaign_status(campaign_id, status):
    """Updates campaign status."""
    query("UPDATE email_campaigns SET status = ? WHERE id = ?", (status, campaign_id))

def update_campaign_sent_count(campaign_id, sent_count):
    """Updates the sent count for a campaign."""
    query("UPDATE email_campaigns SET sent_count = ? WHERE id = ?", (sent_count, campaign_id))

def get_campaign_emails(campaign_id):
    """Gets all sent_emails for a campaign."""
    rows = query(
        "SELECT * FROM sent_emails WHERE campaign_id = ? ORDER BY id",
        (campaign_id,)
    )
    return [convert_datetime_to_str(dict(r)) for r in rows]

def update_sent_email(sent_email_id, **kwargs):
    """Updates a sent_email record with the provided fields."""
    if not kwargs:
        return

    set_clauses = []
    params = []
    for key, value in kwargs.items():
        set_clauses.append(f"{key} = ?")
        params.append(value)

    params.append(sent_email_id)
    query(f"UPDATE sent_emails SET {', '.join(set_clauses)} WHERE id = ?", tuple(params))

def get_sent_email_by_message_id(sendgrid_message_id):
    """Gets a sent_email by SendGrid message ID."""
    rows = query(
        "SELECT * FROM sent_emails WHERE sendgrid_message_id = ?",
        (sendgrid_message_id,)
    )
    if rows:
        return convert_datetime_to_str(dict(rows[0]))
    return None

def record_email_event(sent_email_id, sendgrid_message_id, event_type, event_data=None):
    """Records an email event from webhook."""
    query('''
        INSERT INTO email_events (sent_email_id, sendgrid_message_id, event_type, event_data)
        VALUES (?, ?, ?, ?)
    ''', (sent_email_id, sendgrid_message_id, event_type, json.dumps(event_data) if event_data else None))

def get_campaign_stats(team_name):
    """Gets aggregated campaign statistics for a team."""
    rows = query('''
        SELECT
            COUNT(*) as total_campaigns,
            COALESCE(SUM(total_recipients), 0) as total_recipients,
            COALESCE(SUM(sent_count), 0) as total_sent
        FROM email_campaigns
        WHERE team_name = ?
    ''', (team_name,))

    if not rows:
        return {'total_campaigns': 0, 'total_recipients': 0, 'total_sent': 0, 'total_opened': 0, 'total_clicked': 0}

    stats = dict(rows[0])

    # Get open/click counts
    open_rows = query('''
        SELECT COUNT(*) as count FROM sent_emails se
        JOIN email_campaigns ec ON se.campaign_id = ec.id
        WHERE ec.team_name = ? AND se.opened_at IS NOT NULL
    ''', (team_name,))

    click_rows = query('''
        SELECT COUNT(*) as count FROM sent_emails se
        JOIN email_campaigns ec ON se.campaign_id = ec.id
        WHERE ec.team_name = ? AND se.clicked_at IS NOT NULL
    ''', (team_name,))

    stats['total_opened'] = open_rows[0]['count'] if open_rows else 0
    stats['total_clicked'] = click_rows[0]['count'] if click_rows else 0

    return stats


# --- USER ROLE FUNCTIONS ---

def get_user_role(email):
    """Gets the role of a user (pm or consultant)."""
    user = get_user(email)
    if user:
        return user.get('role', 'consultant')
    return 'consultant'

def set_user_role(email, role):
    """Sets the role of a user."""
    if role not in ('pm', 'consultant'):
        raise ValueError("Role must be 'pm' or 'consultant'")
    query("UPDATE users SET role = ? WHERE email = ?", (role, email))

def is_pm(email):
    """Checks if a user is a PM."""
    return get_user_role(email) == 'pm'


# --- SENDGRID KEY FUNCTIONS ---

def save_sendgrid_key(email, sendgrid_api_key):
    """Saves encrypted SendGrid API key for a user."""
    query('''
        UPDATE user_keys
        SET sendgrid_api_key_enc = ?
        WHERE user_email = ?
    ''', (encrypt_key(sendgrid_api_key), email))

def get_sendgrid_key(email):
    """Retrieves and decrypts SendGrid API key for a user."""
    rows = query("SELECT sendgrid_api_key_enc FROM user_keys WHERE user_email = ?", (email,))
    if not rows or not rows[0].get('sendgrid_api_key_enc'):
        return None
    return decrypt_key(rows[0]['sendgrid_api_key_enc'])
