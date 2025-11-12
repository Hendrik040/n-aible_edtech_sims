#!/usr/bin/env python3
"""
Clean up test users created for load testing

Usage:
    python scripts/cleanup_test_users.py  # Delete all test users
    python scripts/cleanup_test_users.py --confirm  # Require confirmation
"""

import sys
import argparse
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from database.connection import get_db_session
from database.models import User

def cleanup_test_users(confirm: bool = False):
    """Delete all test users from the database"""
    with get_db_session() as db:
        test_users = db.query(User).filter(User.email.like('teststudent%@test.com')).all()
        
        if not test_users:
            print("✅ No test users found in database")
            return
        
        print(f"🗑️  Found {len(test_users)} test users to delete:")
        print(f"   Pattern: teststudent*@test.com")
        print()
        
        if not confirm:
            response = input("⚠️  Are you sure you want to delete these users? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Cancelled. No users deleted.")
                return
        
        deleted = 0
        for user in test_users:
            print(f"   Deleting: {user.email}")
            db.delete(user)
            deleted += 1
        
        db.commit()
        print(f"\n✅ Deleted {deleted} test users")

def main():
    parser = argparse.ArgumentParser(description="Clean up test users from database")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    cleanup_test_users(confirm=args.confirm)

if __name__ == "__main__":
    main()

