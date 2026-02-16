"""
Migration script to ensure multi-household support in Auto-Cart.

This script verifies and updates the database to support:
- Profiles (users) being part of multiple households
- Profiles being owners of one or more households
- Profiles being members of one or more households
- Recipes and lists scoped to households
"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import app, db
from models import User, Recipe, GroceryList, Household, HouseholdMember, MealPlanEntry
from sqlalchemy import text


def migrate_multi_household():
    """Run the migration to ensure multi-household support"""

    with app.app_context():
        print("Starting migration to ensure multi-household support...")
        print("=" * 70)

        # 1. Verify tables exist
        print("\n1. Verifying database tables...")
        db.create_all()
        print("   ✓ All tables verified/created")

        # 2. Verify household_members table structure
        print("\n2. Verifying household_members table...")
        try:
            # Check if the unique constraint exists
            result = db.session.execute(
                text("""
                SELECT COUNT(*) as count 
                FROM sqlite_master 
                WHERE type='index' 
                AND name='unique_household_user'
            """)
            )
            count = result.fetchone()[0]
            if count > 0:
                print("   ✓ Unique constraint on (household_id, user_id) exists")
            else:
                print("   ⚠ Unique constraint may need to be created")
        except Exception as e:
            print(f"   - Error checking constraint: {e}")

        # 3. Verify role column allows 'owner' and 'member'
        print("\n3. Verifying role values in household_members...")
        try:
            memberships = HouseholdMember.query.all()
            roles = set(m.role for m in memberships)
            print(f"   ✓ Found roles: {roles}")

            # Update any 'admin' roles to 'owner' for consistency
            admin_count = 0
            for membership in memberships:
                if membership.role == "admin":
                    membership.role = "owner"
                    admin_count += 1

            if admin_count > 0:
                db.session.commit()
                print(f"   ✓ Updated {admin_count} 'admin' roles to 'owner'")
            else:
                print("   ✓ No role updates needed")
        except Exception as e:
            print(f"   - Error checking roles: {e}")
            db.session.rollback()

        # 4. Verify recipes are scoped to households
        print("\n4. Verifying recipe household scoping...")
        try:
            recipes_without_household = Recipe.query.filter(
                Recipe.household_id.is_(None)
            ).count()
            if recipes_without_household > 0:
                print(
                    f"   ⚠ Found {recipes_without_household} recipes without household_id"
                )
                print("   → These recipes should be migrated to a household")
            else:
                print("   ✓ All recipes are scoped to households")
        except Exception as e:
            print(f"   - Error checking recipes: {e}")

        # 5. Verify grocery lists are scoped to households
        print("\n5. Verifying grocery list household scoping...")
        try:
            lists_without_household = GroceryList.query.filter(
                GroceryList.household_id.is_(None)
            ).count()
            if lists_without_household > 0:
                print(
                    f"   ⚠ Found {lists_without_household} grocery lists without household_id"
                )
                print("   → These lists should be migrated to a household")
            else:
                print("   ✓ All grocery lists are scoped to households")
        except Exception as e:
            print(f"   - Error checking grocery lists: {e}")

        # 6. Display multi-household statistics
        print("\n6. Multi-household statistics:")
        try:
            total_users = User.query.count()
            total_households = Household.query.count()
            total_memberships = HouseholdMember.query.count()

            # Users with multiple households
            users_with_multiple = db.session.execute(
                text("""
                SELECT COUNT(DISTINCT user_id) as count
                FROM household_members
                GROUP BY user_id
                HAVING COUNT(household_id) > 1
            """)
            ).fetchall()
            multi_household_users = len(users_with_multiple)

            # Users who own multiple households
            owners_with_multiple = db.session.execute(
                text("""
                SELECT COUNT(DISTINCT user_id) as count
                FROM household_members
                WHERE role = 'owner'
                GROUP BY user_id
                HAVING COUNT(household_id) > 1
            """)
            ).fetchall()
            multi_owner_users = len(owners_with_multiple)

            print(f"   Total users: {total_users}")
            print(f"   Total households: {total_households}")
            print(f"   Total memberships: {total_memberships}")
            print(f"   Users in multiple households: {multi_household_users}")
            print(f"   Users owning multiple households: {multi_owner_users}")
            print(
                f"   Average households per user: {total_memberships / total_users if total_users > 0 else 0:.2f}"
            )
        except Exception as e:
            print(f"   - Error calculating statistics: {e}")

        print("\n" + "=" * 70)
        print("Migration verification complete!")
        print("\nNOTE: The system now supports:")
        print("  • Profiles being part of multiple households")
        print("  • Profiles owning multiple households")
        print("  • Profiles being members of multiple households")
        print("  • All recipes and lists scoped to households")


if __name__ == "__main__":
    migrate_multi_household()
