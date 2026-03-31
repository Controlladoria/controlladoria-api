#!/usr/bin/env python3
"""
Make User Admin Script
Creates or promotes a user to admin role

Usage:
    python scripts/make_admin.py <email>

Example:
    python scripts/make_admin.py admin@dresystem.com
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.security import hash_password
from database import SessionLocal, User


def make_admin(email: str, create_if_not_exists: bool = False):
    """
    Make a user admin by email

    Args:
        email: User email address
        create_if_not_exists: If True, create user if doesn't exist
    """
    db = SessionLocal()

    try:
        # Find user by email
        user = db.query(User).filter(User.email == email).first()

        if not user:
            if create_if_not_exists:
                print(f"User '{email}' not found. Creating new admin user...")

                # Prompt for password
                import getpass

                password = getpass.getpass("Enter password for new admin user: ")
                confirm_password = getpass.getpass("Confirm password: ")

                if password != confirm_password:
                    print("❌ Error: Passwords do not match!")
                    return False

                if len(password) < 8:
                    print("❌ Error: Password must be at least 8 characters!")
                    return False

                # Prompt for name
                full_name = input("Enter full name (optional): ").strip() or None
                company_name = input("Enter company name (optional): ").strip() or None

                # Create user
                user = User(
                    email=email,
                    password_hash=hash_password(password),
                    full_name=full_name,
                    company_name=company_name,
                    is_active=True,
                    is_verified=True,  # Auto-verify admin
                    is_admin=True,
                )

                db.add(user)
                db.commit()
                db.refresh(user)

                print(f"✅ Admin user created successfully!")
                print(f"   Email: {user.email}")
                print(f"   Name: {user.full_name or 'Not set'}")
                print(f"   Admin: {user.is_admin}")

                return True
            else:
                print(f"❌ Error: User '{email}' not found!")
                print(f"   Use --create flag to create a new admin user.")
                return False

        # User exists - check if already admin
        if user.is_admin:
            print(f"ℹ️  User '{email}' is already an admin!")
            print(f"   Name: {user.full_name or 'Not set'}")
            print(f"   Active: {user.is_active}")
            return True

        # Promote to admin
        print(f"Promoting '{email}' to admin...")
        user.is_admin = True
        db.commit()

        print(f"✅ User promoted to admin successfully!")
        print(f"   Email: {user.email}")
        print(f"   Name: {user.full_name or 'Not set'}")
        print(f"   Admin: {user.is_admin}")

        return True

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        db.rollback()
        return False

    finally:
        db.close()


def list_admins():
    """List all admin users"""
    db = SessionLocal()

    try:
        admins = db.query(User).filter(User.is_admin == True).all()

        if not admins:
            print("No admin users found.")
            return

        print(f"\n📋 Admin Users ({len(admins)}):")
        print("-" * 80)

        for admin in admins:
            print(f"  Email: {admin.email}")
            print(f"  Name: {admin.full_name or 'Not set'}")
            print(f"  Active: {'Yes' if admin.is_active else 'No'}")
            print(f"  Created: {admin.created_at.strftime('%Y-%m-%d')}")
            print("-" * 80)

    finally:
        db.close()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Make a user admin in DreSystem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Promote existing user to admin
  python scripts/make_admin.py admin@dresystem.com

  # Create new admin user if doesn't exist
  python scripts/make_admin.py admin@dresystem.com --create

  # List all admin users
  python scripts/make_admin.py --list
""",
    )

    parser.add_argument("email", nargs="?", help="Email address of user to make admin")

    parser.add_argument(
        "--create", action="store_true", help="Create user if doesn't exist"
    )

    parser.add_argument("--list", action="store_true", help="List all admin users")

    args = parser.parse_args()

    # List admins
    if args.list:
        list_admins()
        return

    # Email is required if not listing
    if not args.email:
        parser.print_help()
        sys.exit(1)

    # Make admin
    success = make_admin(args.email, create_if_not_exists=args.create)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
