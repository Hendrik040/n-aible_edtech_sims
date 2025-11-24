#!/usr/bin/env python3
"""
Create test users for load testing

Usage:
    python scripts/create_test_users.py --count 50 --role student
    python scripts/create_test_users.py --count 30 --role student --password mypassword
"""

import sys
import argparse
import os
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from database.connection import get_db_session
from database.models import User
from common.utils.auth import get_password_hash

def create_test_users(count: int, role: str = "student", password: str = None):
    """Create test users in the database"""
    # Get password from environment or use default
    if password is None:
        password = os.getenv("TEST_USER_PASSWORD", "testpass123")
    
    # Security: Warn if using default password
    if password == "testpass123":
        print("⚠️  WARNING: Using default password 'testpass123'")
        print("   Set TEST_USER_PASSWORD environment variable for custom password")
        print("   Example: export TEST_USER_PASSWORD='your_secure_password'")
        print()
    
    created = 0
    skipped = 0
    
    with get_db_session() as db:
        for i in range(1, count + 1):
            email = f"teststudent{i}@test.com"
            username = f"teststudent{i}"
            
            # Check if user already exists
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                print(f"⏭️  User {email} already exists, skipping...")
                skipped += 1
                continue
            
            # Generate role-based user ID
            from common.utils.id_generator import generate_unique_user_id
            try:
                user_id = generate_unique_user_id(db, role)
            except Exception as e:
                print(f"❌ Failed to generate user ID for {email}: {e}")
                continue
            
            # Create user
            user = User(
                user_id=user_id,
                email=email,
                username=username,
                full_name=f"Test Student {i}",
                password_hash=get_password_hash(password),
                role=role,
                is_active=True,
                is_verified=True
            )
            
            db.add(user)
            created += 1
            print(f"✅ Created user {i}/{count}: {email} (ID: {user_id})")
        
        db.commit()
    
    print(f"\n📊 Summary:")
    print(f"   Created: {created}")
    print(f"   Skipped: {skipped}")
    print(f"   Total: {count}")
    # Only print password if explicitly requested (not in production)
    if os.getenv("SHOW_TEST_PASSWORD", "").lower() == "true":
        print(f"\n✅ Test users ready! Use password: {password}")
    else:
        print(f"\n✅ Test users ready! Password set (use SHOW_TEST_PASSWORD=true to display)")

def main():
    parser = argparse.ArgumentParser(description="Create test users for load testing")
    parser.add_argument("--count", type=int, default=50, help="Number of test users to create")
    parser.add_argument("--role", type=str, default="student", choices=["student", "professor", "admin"], help="User role")
    parser.add_argument("--password", type=str, default=None, help="Password for all test users (default: from TEST_USER_PASSWORD env or 'testpass123')")
    
    args = parser.parse_args()
    
    print(f"👥 Creating {args.count} test users with role '{args.role}'...")
    print()
    
    create_test_users(args.count, args.role, args.password)

if __name__ == "__main__":
    main()

