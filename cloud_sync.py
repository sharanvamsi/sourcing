import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load local environment if exists
load_dotenv()

def push_to_cloud():
    print("🚀 ABA Sourcing Cloud Sync Utility")
    print("----------------------------------")
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url or "railway.internal" in db_url:
        print("⚠️  Warning: For local sync, you MUST use the EXTERNAL Database URL from Railway.")
        print("   (Go to Railway -> Postgres -> Connect -> External Database URL)")
        db_url = input("\nPlease paste your EXTERNAL Railway Connection URL: ").strip()
    
    if not db_url:
        print("❌ Aborted.")
        return

    try:
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        conn.autocommit = True
        cursor = conn.cursor()
        print("✅ Connected to Cloud Database.")

        # 1. Migrate Roster
        if os.path.exists("roster.json"):
            with open("roster.json", "r") as f:
                roster = json.load(f)
            
            print(f"📦 Syncing {len(roster)} users...")
            for user in roster:
                email = user['email'].lower().strip()
                is_admin = user.get('is_admin', False)
                cursor.execute('''
                    INSERT INTO users (email, name, team_name, is_admin)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(email) DO UPDATE SET name=EXCLUDED.name, team_name=EXCLUDED.team_name, is_admin=EXCLUDED.is_admin
                ''', (email, user['name'], user['team_name'], is_admin))
            print("✅ Roster Synced.")

        # 2. Migrate Blacklist
        if os.path.exists("blacklist.json"):
            with open("blacklist.json", "r") as f:
                blacklist = json.load(f)
            print(f"📦 Syncing {len(blacklist)} blacklisted domains...")
            for domain in blacklist:
                cursor.execute("INSERT INTO blacklist (domain) VALUES (%s) ON CONFLICT DO NOTHING", (domain.lower().strip(),))
            print("✅ Blacklist Synced.")

        conn.close()
        print("\n✨ Sync Complete! Your production database is now populated.")
        print("You can now log in at your Railway URL.")

    except Exception as e:
        print(f"❌ Error during sync: {e}")

if __name__ == "__main__":
    push_to_cloud()
