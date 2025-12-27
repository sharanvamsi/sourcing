#!/usr/bin/env python3
"""
Migration script to transfer data from JSON files to SQLite database for local development.
This script migrates:
- roster.json -> users table
- blacklist.json -> blacklist table
- domain_cache.json -> domain_cache table
- keys.json -> user_keys table (converts to single API key format)
"""

import json
import os
import sys
from pathlib import Path
from db_manager import (
    init_db, add_user, add_to_blacklist, update_domain_cache,
    save_user_keys, get_all_users, get_blacklist, get_cached_domain,
    get_user_keys
)
from security_manager import encrypt_key

def migrate_roster():
    """Migrate users from roster.json to users table."""
    roster_file = Path("roster.json")
    
    if not roster_file.exists():
        print("⚠️  roster.json not found, skipping user migration")
        return 0
    
    try:
        with open(roster_file, 'r') as f:
            roster_data = json.load(f)
        
        existing_users = get_all_users()
        existing_emails = {user['email'] for user in existing_users} if existing_users else set()
        
        migrated = 0
        skipped = 0
        
        for entry in roster_data:
            email = entry.get('email', '').lower().strip()
            if not email:
                continue
            
            if email in existing_emails:
                skipped += 1
                continue
            
            name = entry.get('name', '')
            team_name = entry.get('team_name', '')
            is_admin = entry.get('is_admin', False)
            
            # Mark Exec Board as admin by default
            if not is_admin and team_name == "Exec Board":
                is_admin = True
            
            add_user(email, name, team_name, is_admin=is_admin)
            migrated += 1
        
        print(f"✅ Migrated {migrated} users from roster.json")
        if skipped > 0:
            print(f"   Skipped {skipped} users (already exist)")
        return migrated
        
    except Exception as e:
        print(f"❌ Error migrating roster: {e}")
        return 0

def migrate_blacklist():
    """Migrate domains from blacklist.json to blacklist table."""
    blacklist_file = Path("blacklist.json")
    
    if not blacklist_file.exists():
        print("⚠️  blacklist.json not found, skipping blacklist migration")
        return 0
    
    try:
        with open(blacklist_file, 'r') as f:
            blacklist_data = json.load(f)
        
        existing_blacklist = get_blacklist()
        existing_domains = set(existing_blacklist) if existing_blacklist else set()
        
        migrated = 0
        skipped = 0
        
        for domain in blacklist_data:
            if not domain:
                continue
            
            domain_lower = domain.lower().strip()
            if domain_lower in existing_domains:
                skipped += 1
                continue
            
            add_to_blacklist(domain_lower)
            migrated += 1
        
        print(f"✅ Migrated {migrated} domains from blacklist.json")
        if skipped > 0:
            print(f"   Skipped {skipped} domains (already exist)")
        return migrated
        
    except Exception as e:
        print(f"❌ Error migrating blacklist: {e}")
        return 0

def migrate_domain_cache():
    """Migrate domain cache from domain_cache.json to domain_cache table."""
    cache_file = Path("domain_cache.json")
    
    if not cache_file.exists():
        print("⚠️  domain_cache.json not found, skipping domain cache migration")
        return 0
    
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        
        migrated = 0
        skipped = 0
        
        for company_name, domain in cache_data.items():
            if not company_name or not domain:
                continue
            
            # Check if already cached
            existing = get_cached_domain(company_name)
            if existing:
                skipped += 1
                continue
            
            update_domain_cache(company_name, domain)
            migrated += 1
        
        print(f"✅ Migrated {migrated} domain cache entries from domain_cache.json")
        if skipped > 0:
            print(f"   Skipped {skipped} entries (already exist)")
        return migrated
        
    except Exception as e:
        print(f"❌ Error migrating domain cache: {e}")
        return 0

def migrate_keys():
    """Migrate API keys from keys.json to user_keys table."""
    keys_file = Path("keys.json")
    
    if not keys_file.exists():
        print("⚠️  keys.json not found, skipping keys migration")
        return 0
    
    try:
        with open(keys_file, 'r') as f:
            keys_data = json.load(f)
        
        migrated = 0
        skipped = 0
        
        for email, keys_dict in keys_data.items():
            email = email.lower().strip()
            if not email:
                continue
            
            # Check if user already has keys in database
            existing_keys = get_user_keys(email)
            if existing_keys:
                skipped += 1
                continue
            
            # Convert old 3-key format to single key
            # Prefer MIXED_PEOPLE_API_KEY, fallback to others
            api_key = (
                keys_dict.get("MIXED_PEOPLE_API_KEY") or
                keys_dict.get("BULK_MATCH_API_KEY") or
                keys_dict.get("ORG_SEARCH_API_KEY") or
                keys_dict.get("APOLLO_API_KEY")  # New format
            )
            
            if not api_key:
                print(f"⚠️  No API key found for {email}, skipping")
                skipped += 1
                continue
            
            # Save using the new single-key format
            save_user_keys(email, api_key)
            migrated += 1
        
        print(f"✅ Migrated {migrated} user API keys from keys.json")
        if skipped > 0:
            print(f"   Skipped {skipped} users (already have keys)")
        return migrated
        
    except Exception as e:
        print(f"❌ Error migrating keys: {e}")
        return 0

def main():
    """Run all migrations."""
    print("🚀 Starting JSON to Database Migration")
    print("=" * 60)
    
    # Ensure database is initialized
    print("\n📦 Initializing database...")
    init_db()
    print("✅ Database initialized")
    
    # Run migrations
    print("\n📥 Migrating data from JSON files...")
    print("-" * 60)
    
    roster_count = migrate_roster()
    blacklist_count = migrate_blacklist()
    cache_count = migrate_domain_cache()
    keys_count = migrate_keys()
    
    # Summary
    print("\n" + "=" * 60)
    print("✨ Migration Complete!")
    print(f"   Users: {roster_count}")
    print(f"   Blacklist domains: {blacklist_count}")
    print(f"   Domain cache entries: {cache_count}")
    print(f"   API keys: {keys_count}")
    print("=" * 60)
    
    total = roster_count + blacklist_count + cache_count + keys_count
    if total > 0:
        print(f"\n✅ Successfully migrated {total} items to database")
        print("   You can now use the database for local development!")
    else:
        print("\n⚠️  No new data was migrated (all items may already exist)")

if __name__ == "__main__":
    # Check if we're using SQLite (local development)
    if os.getenv("DATABASE_URL"):
        response = input("⚠️  DATABASE_URL is set. This will migrate to PostgreSQL, not SQLite.\n"
                        "   Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Migration cancelled")
            sys.exit(0)
    
    main()

