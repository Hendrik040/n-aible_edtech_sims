#!/usr/bin/env python3
"""
Script to automatically create test accounts for load testing.

This script ONLY creates accounts - it does NOT run simulations.
After creating accounts, use locustfile.py to run load tests.

For students, this simulates the real invite link registration flow:
1. Visit invite link page (validates invite token)
2. Register account from invite page ("Sign Up & Join Cohort")
3. Accept invite link (auto-joins cohort)

This matches what happens when a student visits /invite/{token} and clicks
"Sign Up & Join Cohort" on the frontend.

Usage:
    # Create students via invite link (recommended for load testing)
    # Option 1: Pass full invite link URL
    python load_tests/create_test_accounts.py --count 10 --role student --invite-token "http://localhost:3000/invite/abc123xyz" --base-url http://localhost:8000
    
    # Option 2: Pass just the token
    python load_tests/create_test_accounts.py --count 10 --role student --invite-token abc123xyz --base-url http://localhost:8000
    
    # Option 3: Use environment variable (easiest - just copy/paste the full link)
    export INVITE_LINK="http://localhost:3000/invite/abc123xyz"
    python load_tests/create_test_accounts.py --count 10 --role student --base-url http://localhost:8000
    
    # Create students without invite (direct registration, not in cohort)
    python load_tests/create_test_accounts.py --count 10 --role student --base-url http://localhost:8000
    
After creating accounts, run load tests separately:
    locust -f load_tests/locustfile.py
"""

import argparse
import os
import re
import requests
import sys
from typing import List, Tuple, Optional


def extract_invite_token(invite_input: Optional[str]) -> Optional[str]:
    """
    Extract invite token from either:
    - Full URL: http://localhost:3000/invite/abc123xyz -> abc123xyz
    - Just token: abc123xyz -> abc123xyz
    
    Returns the token or None if input is invalid.
    """
    if not invite_input:
        return None
    
    # If it looks like a URL, extract the token part
    if '/' in invite_input:
        # Match pattern: /invite/{token} or invite/{token}
        match = re.search(r'/invite/([^/?]+)', invite_input)
        if match:
            return match.group(1)
        # If no match, try to get the last part after the last /
        return invite_input.split('/')[-1].split('?')[0]
    
    # Otherwise, assume it's just the token
    return invite_input.strip()


def create_test_account(
    base_url: str,
    email: str,
    password: str,
    role: str,
    index: int,
    invite_token: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Create a single test account following the real invite link flow.
    
    For students with invite_token (simulates visiting invite page):
    1. Validate invite link (GET /invites/{token}) - like visiting the invite page
    2. Register account from invite page (POST /api/auth/users/register)
    3. Login to get session (POST /api/auth/users/login)
    4. Accept the invite link (POST /invites/{token}/accept) - auto-joins cohort
    
    Returns:
        (success: bool, message: str)
    """
    session = requests.Session()
    
    try:
        # Step 1: For students with invite token, validate the invite link first
        # (simulates visiting the invite page /invite/{token})
        if role == "student" and invite_token:
            invite_info_url = f"{base_url}/invites/{invite_token}"
            invite_info_response = session.get(invite_info_url, timeout=10)
            
            if invite_info_response.status_code != 200:
                return False, f"❌ Invalid invite link for {email}: HTTP {invite_info_response.status_code} - {invite_info_response.text}"
            
            # Invite is valid, proceed with registration
            # (This simulates the student seeing the invite page and clicking "Sign Up & Join Cohort")
        
        # Step 2: Register account from the invite page
        # (simulates filling out the "Sign Up & Join Cohort" form on /invite/{token})
        # Generate username from email (like frontend does)
        username = email.lower().replace('@', '_').replace('.', '_').replace('-', '_')
        # Remove any invalid characters
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        register_url = f"{base_url}/api/auth/users/register"
        payload = {
            "email": email,
            "full_name": f"Test {role.title()} {index}",
            "username": username,
            "password": password,
            "role": role,
            "bio": f"Automated test account for load testing",
            "profile_public": True,
            "allow_contact": True  # Match frontend default
        }
        
        response = session.post(register_url, json=payload, timeout=10)
        
        if response.status_code == 200:
            account_created = True
        elif response.status_code == 400:
            # Account might already exist
            error_detail = response.json().get("detail", "Unknown error")
            if "already" in error_detail.lower():
                account_created = True  # Account exists, continue to accept invite
            else:
                return False, f"❌ Failed to create {email}: {error_detail}"
        else:
            return False, f"❌ Failed to create {email}: HTTP {response.status_code} - {response.text}"
        
        # Step 3: If student and invite_token provided, login and accept invite
        # (simulates auto-accept after registration - the invite page automatically accepts the invite)
        if role == "student" and invite_token:
            # Login to get session cookie (required to accept invite)
            login_url = f"{base_url}/api/auth/users/login"
            login_payload = {"email": email, "password": password}
            
            login_response = session.post(login_url, json=login_payload, timeout=10)
            
            if login_response.status_code != 200:
                return False, f"❌ Failed to login {email} after registration: {login_response.text}"
            
            # Accept the invite link using the token (POST /invites/{token}/accept)
            # This is what happens when you register from the invite page - it auto-joins the cohort
            accept_url = f"{base_url}/invites/{invite_token}/accept"
            accept_response = session.post(accept_url, timeout=10)
            
            if accept_response.status_code == 200:
                accept_data = accept_response.json()
                if accept_data.get("already_enrolled"):
                    return True, f"✅ {email} created and already in cohort"
                else:
                    return True, f"✅ Created {email} and joined cohort via invite"
            elif accept_response.status_code == 410:
                return False, f"❌ Invite link expired or used up for {email}"
            else:
                return False, f"❌ Failed to accept invite for {email}: HTTP {accept_response.status_code} - {accept_response.text}"
        
        return True, f"✅ Created {email}"
        
    except requests.exceptions.RequestException as e:
        return False, f"❌ Network error creating {email}: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Create test accounts for load testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create 10 student accounts
  python load_tests/create_test_accounts.py --count 10 --role student

  # Create 5 professor accounts with custom base URL
  python load_tests/create_test_accounts.py --count 5 --role professor --base-url https://your-backend.up.railway.app

  # Create accounts with custom email prefix
  python load_tests/create_test_accounts.py --count 10 --role student --email-prefix loadtest_student
        """
    )
    
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of test accounts to create"
    )
    
    parser.add_argument(
        "--role",
        type=str,
        choices=["student", "professor"],
        required=True,
        help="Role for the test accounts"
    )
    
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the backend API (default: http://localhost:8000)"
    )
    
    parser.add_argument(
        "--email-prefix",
        type=str,
        default=None,
        help="Email prefix (default: 'student' or 'prof' based on role)"
    )
    
    parser.add_argument(
        "--password-prefix",
        type=str,
        default="password",
        help="Password prefix (default: 'password')"
    )
    
    parser.add_argument(
        "--domain",
        type=str,
        default="test.com",
        help="Email domain (default: 'test.com')"
    )
    
    parser.add_argument(
        "--invite-token",
        type=str,
        default=None,
        help="Cohort invite token OR full invite link URL (e.g., http://localhost:3000/invite/abc123xyz). Can also use INVITE_LINK env var."
    )
    
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Starting index for account numbering (default: 1). Use this to create accounts 11-50 if you already have 1-10."
    )
    
    args = parser.parse_args()
    
    # Check for invite link in environment variable if not provided via CLI
    invite_input = args.invite_token or os.getenv("INVITE_LINK")
    
    # Extract token from full URL if needed
    invite_token = extract_invite_token(invite_input) if invite_input else None
    
    # Update args.invite_token with extracted token
    args.invite_token = invite_token
    
    # Validate: students should use invite token for realistic load testing
    if args.role == "student" and not args.invite_token:
        print("⚠️  WARNING: Creating students without invite token.")
        print("   These students will NOT be in any cohort and won't have simulation instances.")
        print("   For realistic load testing, provide invite link via:")
        print("     - --invite-token <token-or-url>")
        print("     - INVITE_LINK environment variable")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    # Set email prefix based on role if not provided
    if args.email_prefix is None:
        args.email_prefix = "student" if args.role == "student" else "prof"
    
    # Create accounts
    start_idx = args.start_index
    end_idx = start_idx + args.count - 1
    print(f"Creating {args.count} {args.role} test accounts...")
    print(f"Base URL: {args.base_url}")
    if args.role == "student" and args.invite_token:
        if invite_input and invite_input != args.invite_token:
            print(f"Invite Link: {invite_input}")
            print(f"Extracted Token: {args.invite_token}")
        else:
            print(f"Invite Token: {args.invite_token}")
        print("   (Students will register via this invite link and join the cohort)")
    elif args.role == "student":
        print("⚠️  No invite token provided - students will NOT be in any cohort")
    print(f"Email format: {args.email_prefix}{start_idx}@{args.domain} through {args.email_prefix}{end_idx}@{args.domain}")
    print(f"Password format: {args.password_prefix}{start_idx} through {args.password_prefix}{end_idx}")
    print("-" * 60)
    
    success_count = 0
    failed_count = 0
    
    for i in range(start_idx, start_idx + args.count):
        email = f"{args.email_prefix}{i}@{args.domain}"
        password = f"{args.password_prefix}{i}"
        
        success, message = create_test_account(
            args.base_url,
            email,
            password,
            args.role,
            i,
            invite_token=args.invite_token
        )
        
        print(message)
        
        if success:
            success_count += 1
        else:
            failed_count += 1
    
    print("-" * 60)
    print(f"✅ Successfully created/skipped: {success_count}")
    if failed_count > 0:
        print(f"❌ Failed: {failed_count}")
        sys.exit(1)
    
    # Print the .env format
    print("\n" + "=" * 60)
    print("Add these to your .env file:")
    print("=" * 60)
    
    emails = ",".join([f"{args.email_prefix}{i}@{args.domain}" for i in range(start_idx, start_idx + args.count)])
    passwords = ",".join([f"{args.password_prefix}{i}" for i in range(start_idx, start_idx + args.count)])
    
    if args.role == "student":
        print(f"LOADTEST_STUDENT_EMAILS={emails}")
        print(f"LOADTEST_STUDENT_PASSWORDS={passwords}")
    else:
        print(f"LOADTEST_PROFESSOR_EMAILS={emails}")
        print(f"LOADTEST_PROFESSOR_PASSWORDS={passwords}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
