"""
Create System Admin Account

Run this script to create your first sysadmin account.
Only run this manually - never exposed via API.

Usage:
    python create_sysadmin.py --email you@dresystem.com --name "Your Name"
"""

import argparse
from database import SessionLocal
from database_sysadmin import SystemAdmin, SystemAdminPermission
from auth.sysadmin_auth import hash_password


def create_sysadmin(email: str, full_name: str, password: str, is_super_admin: bool = True):
    """Create a system admin account"""
    db = SessionLocal()

    try:
        # Check if sysadmin already exists
        existing = db.query(SystemAdmin).filter(SystemAdmin.email == email).first()
        if existing:
            print(f"❌ System admin with email {email} already exists!")
            return False

        # Create sysadmin
        sysadmin = SystemAdmin(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_active=True,
            is_super_admin=is_super_admin,
            permissions=[p.value for p in SystemAdminPermission] if is_super_admin else [],
            mfa_enabled=False,  # Can enable later
        )

        db.add(sysadmin)
        db.commit()
        db.refresh(sysadmin)

        print("\n✅ System Admin created successfully!")
        print(f"   Email: {sysadmin.email}")
        print(f"   Name: {sysadmin.full_name}")
        print(f"   Super Admin: {sysadmin.is_super_admin}")
        print(f"   Permissions: {len(sysadmin.permissions)} permissions granted")
        print("\n⚠️  IMPORTANT: Enable MFA after first login!")
        print(f"\n🔐 Login at: {settings.sysadmin_frontend_url_dev}/login")
        print(f"   Email: {email}")
        print(f"   Password: {password}")

        return True

    except Exception as e:
        db.rollback()
        print(f"❌ Error creating sysadmin: {e}")
        return False

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create system admin account")
    parser.add_argument("--email", required=True, help="System admin email")
    parser.add_argument("--name", required=True, help="Full name")
    parser.add_argument("--password", help="Password (will prompt if not provided)")
    parser.add_argument("--regular", action="store_true", help="Create regular admin (not super admin)")

    args = parser.parse_args()

    # Get password securely if not provided
    if not args.password:
        import getpass
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm password: ")

        if password != password_confirm:
            print("❌ Passwords don't match!")
            exit(1)
    else:
        password = args.password

    # Import settings after argparse to avoid issues
    from config import settings

    # Create sysadmin
    success = create_sysadmin(
        email=args.email,
        full_name=args.name,
        password=password,
        is_super_admin=not args.regular
    )

    exit(0 if success else 1)
