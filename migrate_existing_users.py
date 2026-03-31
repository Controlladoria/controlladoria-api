"""
Data Migration: Add subscriptions to existing users who don't have them
"""

from datetime import datetime, timedelta
from database import SessionLocal, User, Subscription
from config import settings

def migrate():
    db = SessionLocal()

    try:
        print("=" * 60)
        print("MIGRATION: Add Subscriptions to Existing Users")
        print("=" * 60)

        # Get all users
        users = db.query(User).all()
        print(f"\nFound {len(users)} total users")

        for user in users:
            # Check if user already has a subscription
            existing_sub = db.query(Subscription).filter_by(user_id=user.id).first()

            if existing_sub:
                print(f"  User {user.email}: already has subscription (ID: {existing_sub.id})")
                continue

            # Only create subscriptions for super_admins
            if user.role != "super_admin":
                print(f"  User {user.email}: member role, skipping (shares parent's subscription)")
                continue

            # Create trial subscription
            trial_end = user.trial_end_date or (datetime.utcnow() + timedelta(days=settings.stripe_trial_days))

            subscription = Subscription(
                user_id=user.id,
                stripe_customer_id="",  # Empty string for trial users (will be set when they subscribe)
                stripe_subscription_id=None,
                stripe_price_id=None,
                status="trialing",
                trial_start=datetime.utcnow(),
                trial_end=trial_end,
                current_period_start=datetime.utcnow(),
                current_period_end=trial_end,
                max_users=1,  # Default to 1 user
            )

            db.add(subscription)
            print(f"  User {user.email}: created trial subscription (expires {trial_end.strftime('%Y-%m-%d')})")

        db.commit()

        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE!")
        print("=" * 60)

        # Show summary
        all_subs = db.query(Subscription).all()
        print(f"\nTotal subscriptions: {len(all_subs)}")
        for sub in all_subs:
            user = db.query(User).filter_by(id=sub.user_id).first()
            print(f"  - User: {user.email}, Status: {sub.status}, Max Users: {sub.max_users}")

    except Exception as e:
        print(f"\nERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
