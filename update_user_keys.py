#!/usr/bin/env python3
"""
Script to update user_keys table with a shared API key for all users in roster.json.
All users will be assigned the same API key: 0Hit9o6PW5IVnXpqJvkuPg

REQUIRED ENVIRONMENT VARIABLES:
- DATABASE_URL: PostgreSQL connection string for production database
- MASTER_ENCRYPTION_SECRET: Master secret for encrypting API keys

Usage:
    export DATABASE_URL="postgresql://..."
    export MASTER_ENCRYPTION_SECRET="..."
    python update_user_keys.py
"""

import json
import os
import sys
import argparse
from pathlib import Path

# Try to load .env file if available (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from db_manager import init_db, save_user_keys

def check_environment():
    """Check that required environment variables are set"""
    missing = []
    
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")
    
    if not os.getenv("MASTER_ENCRYPTION_SECRET"):
        missing.append("MASTER_ENCRYPTION_SECRET")
    
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nPlease set these before running the script.")
        return False
    
    return True

def preview_updates(roster_data):
    """Show a preview of what will be updated"""
    print("\n📋 Preview of updates:")
    print("-" * 60)
    for entry in roster_data:
        email = entry.get('email', '').strip()
        name = entry.get('name', 'Unknown')
        if email:
            print(f"  • {email} ({name})")
    print("-" * 60)
    print(f"Total: {len(roster_data)} users\n")

def update_user_keys_from_roster(api_key, confirm=True):
    """Update API keys for all users in roster.json to use the specified API key"""
    roster_file = Path("json-data/roster.json")
    
    if not roster_file.exists():
        print(f"⚠️  {roster_file} not found")
        return False
    
    try:
        # Load roster data
        with open(roster_file, 'r') as f:
            roster_data = json.load(f)
        
        # Show preview
        preview_updates(roster_data)
        
        # Get confirmation
        if confirm:
            database_url = os.getenv("DATABASE_URL", "")
            db_display = database_url[:50] + "..." if len(database_url) > 50 else database_url
            print(f"⚠️  WARNING: This will update the production database!")
            print(f"   Database: {db_display}")
            print(f"   API Key: {api_key}")
            print(f"   Total users to update: {len(roster_data)}")
            response = input("\n⚠️  Type 'YES' to confirm: ").strip()
            if response != "YES":
                print("❌ Aborted by user")
                return False
        
        # Initialize database to ensure tables exist
        print("\n🔌 Connecting to database...")
        init_db()
        print("✅ Database connected\n")
        
        updated = 0
        errors = 0
        
        print(f"Updating API keys for {len(roster_data)} users...")
        print("-" * 60)
        
        for entry in roster_data:
            email = entry.get('email', '').strip()
            if not email:
                print(f"⚠️  Skipping entry with no email: {entry}")
                errors += 1
                continue
            
            try:
                # save_user_keys handles encryption automatically
                save_user_keys(email, api_key)
                updated += 1
                print(f"✅ Updated {email}")
            except Exception as e:
                print(f"❌ Error updating {email}: {e}")
                errors += 1
        
        print("-" * 60)
        print(f"\n✅ Successfully updated {updated} users")
        if errors > 0:
            print(f"⚠️  {errors} errors encountered")
        return errors == 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update user API keys from roster.json")
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt (use with caution)"
    )
    args = parser.parse_args()
    
    # Set the API key for ALL users
    api_key = "0Hit9o6PW5IVnXpqJvkuPg"
    
    print("=" * 60)
    print("🔑 Update User API Keys Script")
    print("=" * 60)
    
    # Check environment
    if not check_environment():
        sys.exit(1)
    
    database_url = os.getenv("DATABASE_URL", "")
    is_production = "railway" in database_url.lower() or "postgres" in database_url.lower()
    
    if is_production:
        db_display = database_url.split("@")[1].split("/")[0] if "@" in database_url else "Production Database"
        print(f"📊 Target: Production Database ({db_display})")
    else:
        print(f"📊 Target: Local Database")
    
    print(f"🔑 API Key for ALL users: {api_key}")
    print("=" * 60)
    
    # Skip confirmation if --yes flag is provided
    success = update_user_keys_from_roster(api_key, confirm=not args.yes)
    
    if success:
        print("\n✅ All updates completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Some updates failed")
        sys.exit(1)
