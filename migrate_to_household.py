"""
Migration script to add household collaboration features to Auto-Cart.
This script creates new tables and updates existing ones to support multi-user households.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import app, db
from models import (
    User,
    Recipe,
    GroceryList,
    Household,
    HouseholdMember,
    MealPlanEntry,
    GroceryListItem,
)
from sqlalchemy import text


def migrate_to_household():
    """Run the migration to add household features"""

    with app.app_context():
        print("Starting migration to household collaboration features...")

        # Create new tables
        print("\n1. Creating new tables...")
        db.create_all()
        print("   ✓ Tables created")

        # Add new columns to existing tables
        print("\n2. Adding new columns to existing tables...")

        # Add columns to recipes table
        try:
            db.session.execute(
                text("ALTER TABLE recipes ADD COLUMN household_id INTEGER")
            )
            print("   ✓ Added household_id to recipes")
        except Exception as e:
            print(f"   - household_id already exists in recipes or error: {e}")

        try:
            db.session.execute(
                text(
                    "ALTER TABLE recipes ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"
                )
            )
            print("   ✓ Added visibility to recipes")
        except Exception as e:
            print(f"   - visibility already exists in recipes or error: {e}")

        try:
            db.session.execute(
                text("ALTER TABLE recipes ADD COLUMN created_at DATETIME")
            )
            print("   ✓ Added created_at to recipes")
        except Exception as e:
            print(f"   - created_at already exists in recipes or error: {e}")

        # Add columns to grocery_lists table
        try:
            db.session.execute(
                text("ALTER TABLE grocery_lists ADD COLUMN household_id INTEGER")
            )
            print("   ✓ Added household_id to grocery_lists")
        except Exception as e:
            print(f"   - household_id already exists in grocery_lists or error: {e}")

        try:
            db.session.execute(
                text(
                    "ALTER TABLE grocery_lists ADD COLUMN name TEXT DEFAULT 'My Grocery List'"
                )
            )
            print("   ✓ Added name to grocery_lists")
        except Exception as e:
            print(f"   - name already exists in grocery_lists or error: {e}")

        try:
            db.session.execute(
                text(
                    "ALTER TABLE grocery_lists ADD COLUMN status VARCHAR(20) DEFAULT 'planning'"
                )
            )
            print("   ✓ Added status to grocery_lists")
        except Exception as e:
            print(f"   - status already exists in grocery_lists or error: {e}")

        try:
            db.session.execute(text("ALTER TABLE grocery_lists ADD COLUMN store TEXT"))
            print("   ✓ Added store to grocery_lists")
        except Exception as e:
            print(f"   - store already exists in grocery_lists or error: {e}")

        try:
            db.session.execute(
                text("ALTER TABLE grocery_lists ADD COLUMN created_by_user_id INTEGER")
            )
            print("   ✓ Added created_by_user_id to grocery_lists")
        except Exception as e:
            print(
                f"   - created_by_user_id already exists in grocery_lists or error: {e}"
            )

        try:
            db.session.execute(
                text("ALTER TABLE grocery_lists ADD COLUMN created_at DATETIME")
            )
            print("   ✓ Added created_at to grocery_lists")
        except Exception as e:
            print(f"   - created_at already exists in grocery_lists or error: {e}")

        try:
            db.session.execute(
                text("ALTER TABLE grocery_lists ADD COLUMN last_modified_at DATETIME")
            )
            print("   ✓ Added last_modified_at to grocery_lists")
        except Exception as e:
            print(
                f"   - last_modified_at already exists in grocery_lists or error: {e}"
            )

        try:
            db.session.execute(
                text(
                    "ALTER TABLE grocery_lists ADD COLUMN last_modified_by_user_id INTEGER"
                )
            )
            print("   ✓ Added last_modified_by_user_id to grocery_lists")
        except Exception as e:
            print(
                f"   - last_modified_by_user_id already exists in grocery_lists or error: {e}"
            )

        try:
            db.session.execute(
                text("ALTER TABLE grocery_lists ADD COLUMN shopping_user_id INTEGER")
            )
            print("   ✓ Added shopping_user_id to grocery_lists")
        except Exception as e:
            print(
                f"   - shopping_user_id already exists in grocery_lists or error: {e}"
            )

        # Add kroger_user_id to households table
        try:
            db.session.execute(
                text("ALTER TABLE households ADD COLUMN kroger_user_id INTEGER")
            )
            print("   ✓ Added kroger_user_id to households")
        except Exception as e:
            print(f"   - kroger_user_id already exists in households or error: {e}")

        db.session.commit()

        # Migrate existing users to have their own households
        print("\n3. Creating default households for existing users...")
        users = User.query.all()

        for user in users:
            # Check if user already has a household
            existing_membership = HouseholdMember.query.filter_by(
                user_id=user.id
            ).first()
            if existing_membership:
                print(f"   - User {user.username} already has a household, skipping")
                continue

            # Create a household for this user
            household = Household(
                name=f"{user.username}'s Household",
                kroger_user_id=user.id if user.oauth_token else None,
            )
            db.session.add(household)
            db.session.flush()  # Get the household ID

            # Add user as owner of their household
            membership = HouseholdMember(
                household_id=household.id, user_id=user.id, role="owner"
            )
            db.session.add(membership)

            print(f"   ✓ Created household for {user.username}")

        db.session.commit()

        # Update existing recipes to belong to households
        print("\n4. Migrating existing recipes to households...")
        recipes = Recipe.query.filter(Recipe.household_id.is_(None)).all()

        for recipe in recipes:
            # Find the user's household
            membership = HouseholdMember.query.filter_by(user_id=recipe.user_id).first()
            if membership:
                recipe.household_id = membership.household_id
                recipe.visibility = (
                    "household"  # Make existing recipes household-visible by default
                )
                print(f"   ✓ Migrated recipe '{recipe.name}' to household")

        db.session.commit()

        # Update existing grocery lists to belong to households
        print("\n5. Migrating existing grocery lists to households...")
        grocery_lists = GroceryList.query.filter(
            GroceryList.household_id.is_(None)
        ).all()

        for grocery_list in grocery_lists:
            # Find the user's household
            if grocery_list.user_id:
                membership = HouseholdMember.query.filter_by(
                    user_id=grocery_list.user_id
                ).first()
                if membership:
                    grocery_list.household_id = membership.household_id
                    grocery_list.created_by_user_id = grocery_list.user_id
                    grocery_list.name = "My Grocery List"
                    print(f"   ✓ Migrated grocery list #{grocery_list.id} to household")

        db.session.commit()

        # Migrate grocery list items from old association table to new GroceryListItem model
        print("\n6. Migrating grocery list items to new structure...")

        # Check if old association table exists
        try:
            result = db.session.execute(
                text(
                    "SELECT grocery_list_id, recipe_ingredient_id FROM grocery_lists_recipe_ingredients"
                )
            )

            for row in result:
                grocery_list_id, recipe_ingredient_id = row

                # Check if this item already exists in new structure
                existing_item = GroceryListItem.query.filter_by(
                    grocery_list_id=grocery_list_id,
                    recipe_ingredient_id=recipe_ingredient_id,
                ).first()

                if not existing_item:
                    # Get the grocery list to find the user
                    grocery_list = GroceryList.query.get(grocery_list_id)

                    item = GroceryListItem(
                        grocery_list_id=grocery_list_id,
                        recipe_ingredient_id=recipe_ingredient_id,
                        added_by_user_id=grocery_list.user_id if grocery_list else None,
                    )
                    db.session.add(item)

            db.session.commit()
            print("   ✓ Migrated grocery list items")

        except Exception as e:
            print(f"   Note: Could not migrate old grocery list items: {e}")
            print("   This is expected if the old table doesn't exist or is empty")

        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Test the application with household features")
        print("2. Users can now invite others to their households")
        print("3. Recipes and grocery lists are now shared within households")


if __name__ == "__main__":
    migrate_to_household()
