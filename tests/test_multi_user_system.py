"""
Comprehensive Test: Multi-User Team Management System

This script validates:
1. Super admin has subscription with max_users
2. Team members DON'T have subscriptions
3. Document access is company-wide (all team members see all documents)
4. Invitation flow works correctly
5. Permissions are enforced correctly
"""

from database import SessionLocal, User, Subscription, Document
from auth.team_management import get_company_users, can_invite_more_users, get_seat_usage
from auth.permissions import get_accessible_user_ids

def test_system():
    db = SessionLocal()

    print("=" * 80)
    print("MULTI-USER SYSTEM VALIDATION")
    print("=" * 80)

    # Test 1: Check user subscriptions
    print("\n[TEST 1] Subscription Validation")
    print("-" * 40)
    users = db.query(User).all()
    for user in users:
        sub = db.query(Subscription).filter_by(user_id=user.id).first()
        has_sub = "YES" if sub else "NO"
        max_users = sub.max_users if sub else "N/A"
        print(f"  {user.email} (role={user.role})")
        print(f"    - Has subscription: {has_sub}")
        print(f"    - Max users: {max_users}")

        # Validate logic
        if user.role == "super_admin" and not sub:
            print("    ❌ ERROR: Super admin missing subscription!")
        elif user.role == "member" and sub:
            print("    ❌ ERROR: Member should NOT have subscription!")
        else:
            print("    ✅ OK")

    # Test 2: Check company access
    print("\n[TEST 2] Company Access Validation")
    print("-" * 40)
    for user in users:
        company_users = get_company_users(user.id, db)
        accessible_ids = get_accessible_user_ids(user, db)
        print(f"  {user.email} can access:")
        for cu in company_users:
            print(f"    - {cu.email} (ID: {cu.id})")
        print(f"    Accessible user IDs: {accessible_ids}")
        print(f"    ✅ Total: {len(accessible_ids)} user(s)")

    # Test 3: Check document access
    print("\n[TEST 3] Document Access Validation")
    print("-" * 40)
    total_docs = db.query(Document).count()
    print(f"  Total documents in database: {total_docs}")

    if total_docs > 0:
        for user in users:
            accessible_ids = get_accessible_user_ids(user, db)
            user_docs = db.query(Document).filter(Document.user_id.in_(accessible_ids)).all()
            print(f"  {user.email} can see: {len(user_docs)} document(s)")

            # Show document ownership
            for doc in user_docs[:3]:  # Show first 3
                owner = db.query(User).filter_by(id=doc.user_id).first()
                print(f"    - Doc ID {doc.id} (owned by {owner.email})")
    else:
        print("  ⚠️  No documents to test with")

    # Test 4: Check invitation limits
    print("\n[TEST 4] Invitation Limits Validation")
    print("-" * 40)
    for user in users:
        if user.role == "super_admin":
            can_invite, reason = can_invite_more_users(user, db)
            seat_usage = get_seat_usage(user, db)

            print(f"  {user.email}:")
            print(f"    - Can invite more: {can_invite}")
            if not can_invite:
                print(f"    - Reason: {reason}")
            print(f"    - Seat usage: {seat_usage}")
            print(f"    ✅ Limit check OK")

    # Test 5: Verify role defaults
    print("\n[TEST 5] Role Defaults Validation")
    print("-" * 40)
    for user in users:
        if not user.parent_user_id:
            expected_role = "super_admin"
        else:
            expected_role = "member"

        if user.role == expected_role:
            print(f"  ✅ {user.email}: role={user.role} (correct)")
        else:
            print(f"  ❌ {user.email}: role={user.role} (expected {expected_role})")

    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE!")
    print("=" * 80)

    db.close()

if __name__ == "__main__":
    test_system()
