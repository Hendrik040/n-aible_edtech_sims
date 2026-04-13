#!/usr/bin/env python3
"""
Helper script to get an invite token from a professor account.

This script helps you get an invite token for load testing setup.
You need to:
1. Have a professor account
2. Have created a cohort
3. Have created an invite link for that cohort

Usage:
    python load_tests/get_invite_token.py \
        --professor-email prof@example.com \
        --professor-password password \
        --base-url http://localhost:8000
"""

import argparse
import requests
import sys
from typing import Optional, Dict, Any


def login_professor(base_url: str, email: str, password: str) -> requests.Session:
    """Login as professor and return authenticated session."""
    session = requests.Session()
    login_url = f"{base_url}/api/auth/users/login"
    
    response = session.post(login_url, json={"email": email, "password": password}, timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code} - {response.text}")
        sys.exit(1)
    
    print(f"✅ Logged in as professor: {email}")
    return session


def get_cohorts(session: requests.Session, base_url: str) -> list:
    """Get all cohorts for the professor."""
    url = f"{base_url}/api/professor/cohorts/"
    response = session.get(url, timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Failed to get cohorts: {response.status_code} - {response.text}")
        sys.exit(1)
    
    cohorts = response.json()
    return cohorts


def get_invite_links(session: requests.Session, base_url: str, cohort_id: int) -> list:
    """Get invite links for a cohort."""
    url = f"{base_url}/api/professor/cohorts/{cohort_id}/invites"
    response = session.get(url, timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Failed to get invite links: {response.status_code} - {response.text}")
        return []
    
    invites = response.json()
    return invites


def create_invite_link(
    session: requests.Session, 
    base_url: str, 
    cohort_id: int,
    invite_type: str = "MULTI_USE",
    max_uses: Optional[int] = None,
    expires_days: int = 30
) -> Optional[Dict[str, Any]]:
    """Create a new invite link for the cohort."""
    from datetime import datetime, timedelta, timezone
    
    url = f"{base_url}/api/professor/cohorts/{cohort_id}/invites"
    
    payload = {
        "invite_type": invite_type,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
    }
    
    if max_uses is not None:
        payload["max_uses"] = max_uses
    
    response = session.post(url, json=payload, timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Failed to create invite link: {response.status_code} - {response.text}")
        return None
    
    return response.json()


def main():
    parser = argparse.ArgumentParser(
        description="Get or create an invite token for load testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get existing invite token from a cohort
  python load_tests/get_invite_token.py \\
      --professor-email prof@example.com \\
      --professor-password password \\
      --cohort-id 1

  # Create a new multi-use invite link
  python load_tests/get_invite_token.py \\
      --professor-email prof@example.com \\
      --professor-password password \\
      --cohort-id 1 \\
      --create \\
      --max-uses 100

  # List all cohorts and their invite links
  python load_tests/get_invite_token.py \\
      --professor-email prof@example.com \\
      --professor-password password \\
      --list-all
        """
    )
    
    parser.add_argument(
        "--professor-email",
        type=str,
        required=True,
        help="Professor email address"
    )
    
    parser.add_argument(
        "--professor-password",
        type=str,
        required=True,
        help="Professor password"
    )
    
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the backend API (default: http://localhost:8000)"
    )
    
    parser.add_argument(
        "--cohort-id",
        type=int,
        default=None,
        help="Cohort ID to get/create invite for"
    )
    
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all cohorts and their invite links"
    )
    
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new invite link if none exist"
    )
    
    parser.add_argument(
        "--max-uses",
        type=int,
        default=None,
        help="Max uses for new invite link (default: unlimited for MULTI_USE)"
    )
    
    parser.add_argument(
        "--expires-days",
        type=int,
        default=30,
        help="Days until invite expires (default: 30)"
    )
    
    args = parser.parse_args()
    
    # Login
    session = login_professor(args.base_url, args.professor_email, args.professor_password)
    
    # List all cohorts
    if args.list_all:
        cohorts = get_cohorts(session, args.base_url)
        print("\n" + "=" * 60)
        print("COHORTS AND INVITE LINKS")
        print("=" * 60)
        
        for cohort in cohorts:
            print(f"\n📚 Cohort: {cohort.get('title', 'N/A')} (ID: {cohort.get('id')})")
            cohort_id = cohort.get('id')
            if cohort_id:
                invites = get_invite_links(session, args.base_url, cohort_id)
                if invites:
                    for invite in invites:
                        token = invite.get('token', 'N/A')
                        invite_type = invite.get('invite_type', 'N/A')
                        uses_count = invite.get('uses_count', 0)
                        max_uses = invite.get('max_uses', 'Unlimited')
                        expires_at = invite.get('expires_at', 'N/A')
                        print(f"  🔗 Token: {token}")
                        print(f"     Type: {invite_type}, Uses: {uses_count}/{max_uses}, Expires: {expires_at}")
                else:
                    print("  (No invite links)")
        
        print("\n" + "=" * 60)
        return
    
    # Get/create invite for specific cohort
    if not args.cohort_id:
        print("❌ --cohort-id is required (or use --list-all to see available cohorts)")
        sys.exit(1)
    
    invites = get_invite_links(session, args.base_url, args.cohort_id)
    
    # Use existing invite or create new one
    if invites and not args.create:
        # Use first available invite
        invite = invites[0]
        token = invite.get('token')
        print("\n" + "=" * 60)
        print(f"✅ Found invite token for cohort {args.cohort_id}:")
        print("=" * 60)
        print(f"Token: {token}")
        print(f"Type: {invite.get('invite_type')}")
        print(f"Uses: {invite.get('uses_count', 0)}/{invite.get('max_uses', 'Unlimited')}")
        print(f"Expires: {invite.get('expires_at')}")
        print("\nUse this token with create_test_accounts.py:")
        print(f"  --invite-token {token}")
        print("=" * 60)
    elif args.create:
        # Create new invite
        invite = create_invite_link(
            session, 
            args.base_url, 
            args.cohort_id,
            max_uses=args.max_uses,
            expires_days=args.expires_days
        )
        if invite:
            token = invite.get('token')
            print("\n" + "=" * 60)
            print(f"✅ Created new invite token for cohort {args.cohort_id}:")
            print("=" * 60)
            print(f"Token: {token}")
            print(f"Type: {invite.get('invite_type')}")
            print(f"Max Uses: {invite.get('max_uses', 'Unlimited')}")
            print(f"Expires: {invite.get('expires_at')}")
            print("\nUse this token with create_test_accounts.py:")
            print(f"  --invite-token {token}")
            print("=" * 60)
    else:
        print(f"❌ No invite links found for cohort {args.cohort_id}")
        print("   Use --create to create a new invite link")
        sys.exit(1)


if __name__ == "__main__":
    main()
