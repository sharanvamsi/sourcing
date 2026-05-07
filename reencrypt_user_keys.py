#!/usr/bin/env python3
"""
Migration script to re-encrypt all user API keys with the current MASTER_ENCRYPTION_SECRET.

This script is useful after rotating MASTER_ENCRYPTION_SECRET:
1. Set OLD_MASTER_ENCRYPTION_SECRET to the previous secret (for decryption)
2. Set MASTER_ENCRYPTION_SECRET to the new secret (for encryption)
3. Run this script to decrypt all keys with old secret and re-encrypt with new secret

REQUIRED ENVIRONMENT VARIABLES:
- DATABASE_URL: PostgreSQL connection string for production database
- MASTER_ENCRYPTION_SECRET: NEW secret for encrypting keys
- OLD_MASTER_ENCRYPTION_SECRET: OLD secret for decrypting existing keys

Usage:
    export DATABASE_URL="postgresql://..."
    export MASTER_ENCRYPTION_SECRET="new-secret-here"
    export OLD_MASTER_ENCRYPTION_SECRET="old-secret-here"
    python reencrypt_user_keys.py
"""

import os
import sys
import argparse

# Try to load .env file if available (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from db_manager import init_db, get_all_users, get_user_keys, save_user_keys
from security_manager import decrypt_key, encrypt_key

def check_environment():
    """Check that required environment variables are set"""
    missing = []
    
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")
    
    if not os.getenv("MASTER_ENCRYPTION_SECRET"):
        missing.append("MASTER_ENCRYPTION_SECRET")
    
    if not os.getenv("OLD_MASTER_ENCRYPTION_SECRET"):
        missing.append("OLD_MASTER_ENCRYPTION_SECRET")
    
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nPlease set these before running the script.")
        return False
    
    return True

def reencrypt_all_keys(confirm=True):
    """Re-encrypt all user API keys with the new MASTER_ENCRYPTION_SECRET"""
    
    # Check environment
    if not check_environment():
        return False
    
    # Initialize database
    print("\n🔌 Connecting to database...")
    init_db()
    print("✅ Database connected\n")
    
    # Get all users
    users = get_all_users()
    if not users:
        print("⚠️  No users found in database")
        return False
    
    print(f"📋 Found {len(users)} users in database")
    print("-" * 60)
    
    # Show preview
    users_with_keys = []
    users_without_keys = []
    
    for user in users:
        email = user.get('email', '')
        api_key = get_user_keys(email)
        if api_key:
            users_with_keys.append((email, api_key))
        else:
            users_without_keys.append(email)
    
    print(f"\n📊 Preview:")
    print(f"   Users with API keys: {len(users_with_keys)}")
    print(f"   Users without API keys: {len(users_without_keys)}")
    
    if users_without_keys:
        print(f"\n   Users without keys (will be skipped):")
        for email in users_without_keys:
            print(f"     - {email}")
    
    if not users_with_keys:
        print("\n⚠️  No users have API keys to re-encrypt")
        return True
    
    # Get confirmation
    if confirm:
        database_url = os.getenv("DATABASE_URL", "")
        db_display = database_url[:50] + "..." if len(database_url) > 50 else database_url
        print(f"\n⚠️  WARNING: This will re-encrypt all API keys in the database!")
        print(f"   Database: {db_display}")
        print(f"   Users to re-encrypt: {len(users_with_keys)}")
        print(f"   OLD_MASTER_ENCRYPTION_SECRET: {'*' * 20} (set)")
        print(f"   MASTER_ENCRYPTION_SECRET: {'*' * 20} (set)")
        response = input("\n⚠️  Type 'YES' to confirm: ").strip()
        if response != "YES":
            print("❌ Aborted by user")
            return False
    
    # Re-encrypt keys
    print(f"\n🔄 Re-encrypting {len(users_with_keys)} API keys...")
    print("-" * 60)
    
    reencrypted = 0
    errors = 0
    skipped = 0
    
    for email, plaintext_key in users_with_keys:
        try:
            # Verify we can decrypt (should work with OLD_MASTER_ENCRYPTION_SECRET)
            # The get_user_keys already decrypted it, so we have the plaintext
            # Now encrypt with new secret
            new_encrypted = encrypt_key(plaintext_key)
            
            if not new_encrypted:
                print(f"❌ Failed to encrypt key for {email}")
                errors += 1
                continue
            
            # Save the re-encrypted key
            save_user_keys(email, plaintext_key)  # This will encrypt with new MASTER_ENCRYPTION_SECRET
            reencrypted += 1
            print(f"✅ Re-encrypted {email}")
            
        except Exception as e:
            print(f"❌ Error re-encrypting {email}: {e}")
            errors += 1
    
    print("-" * 60)
    print(f"\n✅ Successfully re-encrypted {reencrypted} users")
    if errors > 0:
        print(f"⚠️  {errors} errors encountered")
    if skipped > 0:
        print(f"⚠️  {skipped} users skipped (no keys)")
    
    if reencrypted > 0:
        print(f"\n💡 Next steps:")
        print(f"   1. Verify users can log in and access their API keys")
        print(f"   2. Once verified, you can remove OLD_MASTER_ENCRYPTION_SECRET from environment")
    
    return errors == 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-encrypt all user API keys with new MASTER_ENCRYPTION_SECRET")
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt (use with caution)"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔐 Re-encrypt User API Keys Script")
    print("=" * 60)
    
    database_url = os.getenv("DATABASE_URL", "")
    is_production = "railway" in database_url.lower() or "postgres" in database_url.lower()
    
    if is_production:
        db_display = database_url.split("@")[1].split("/")[0] if "@" in database_url else "Production Database"
        print(f"📊 Target: Production Database ({db_display})")
    else:
        print(f"📊 Target: Local Database")
    print("=" * 60)
    
    success = reencrypt_all_keys(confirm=not args.yes)
    
    if success:
        print("\n✅ Migration completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Migration failed")
        sys.exit(1)


