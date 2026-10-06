#!/usr/bin/env python3
"""
Import full production database from Heroku to local SQLite
"""

import subprocess
import json
from app import app, db
from models import (
    User,
    Household,
    HouseholdMember,
    Recipe,
    RecipeIngredient,
    GroceryList,
    GroceryListItem,
)


def run_heroku_query(query):
    """Run a query on Heroku database and return results"""
    result = subprocess.run(
        ["heroku", "pg:psql", "--app", "auto-cart", "-c", query],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        return None

    return result.stdout


def import_full_database():
    """Import all data from Heroku production database"""

    print("🔄 Importing FULL production database from Heroku...")
    print("⚠️  This will CLEAR your local database and replace it with production data!")
    print()

    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Import cancelled")
        return

    with app.app_context():
        print("\n🗑️  Clearing local database...")

        # Drop all tables and recreate
        db.drop_all()
        db.create_all()

        print("✅ Database cleared and recreated")
        print()

        # Import Users
        print("👥 Importing users...")
        query = "SELECT id, username, email, password, is_admin, oauth_token, refresh_token, profile_id, alexa_access_token, alexa_default_grocery_list_id FROM users ORDER BY id;"
        result = run_heroku_query(query)

        if result:
            lines = [
                l for l in result.split("\n") if "|" in l and not l.startswith("-")
            ]
            user_count = 0

            for line in lines[1:]:  # Skip header
                if not line.strip() or line.startswith("("):
                    continue

                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 5:
                    continue

                try:
                    user = User(
                        id=int(parts[0]),
                        username=parts[1],
                        email=parts[2],
                        password=parts[3],
                        is_admin=parts[4] == "t",
                    )

                    # Optional fields
                    if len(parts) > 5 and parts[5]:
                        user.oauth_token = parts[5]
                    if len(parts) > 6 and parts[6]:
                        user.refresh_token = parts[6]
                    if len(parts) > 7 and parts[7]:
                        user.profile_id = parts[7]
                    if len(parts) > 8 and parts[8]:
                        user.alexa_access_token = parts[8]
                    if len(parts) > 9 and parts[9]:
                        try:
                            user.alexa_default_grocery_list_id = int(parts[9])
                        except (ValueError, TypeError):
                            pass

                    db.session.add(user)
                    user_count += 1
                except Exception as e:
                    print(f"  ⚠️  Error importing user: {e}")
                    continue

            db.session.commit()
            print(f"  ✅ Imported {user_count} users")

        # Import Households
        print("\n🏠 Importing households...")
        query = "SELECT id, name, kroger_user_id FROM households ORDER BY id;"
        result = run_heroku_query(query)

        if result:
            lines = [
                l for l in result.split("\n") if "|" in l and not l.startswith("-")
            ]
            household_count = 0

            for line in lines[1:]:
                if not line.strip() or line.startswith("("):
                    continue

                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 2:
                    continue

                try:
                    household = Household(id=int(parts[0]), name=parts[1])

                    if len(parts) > 2 and parts[2]:
                        try:
                            household.kroger_user_id = int(parts[2])
                        except (ValueError, TypeError):
                            pass

                    db.session.add(household)
                    household_count += 1
                except Exception as e:
                    print(f"  ⚠️  Error importing household: {e}")
                    continue

            db.session.commit()
            print(f"  ✅ Imported {household_count} households")

        # Import Household Members
        print("\n👥 Importing household members...")
        query = (
            "SELECT id, household_id, user_id, role FROM household_members ORDER BY id;"
        )
        result = run_heroku_query(query)
        member_count = 0

        member_count = 0
        if result:
            lines = [
                l for l in result.split("\n") if "|" in l and not l.startswith("-")
            ]

            for line in lines[1:]:
                if not line.strip() or line.startswith("("):
                    continue

                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 4:
                    continue

                try:
                    member = HouseholdMember(
                        id=int(parts[0]),
                        household_id=int(parts[1]),
                        user_id=int(parts[2]),
                        role=parts[3],
                    )

                    db.session.add(member)
                    member_count += 1
                except Exception as e:
                    print(f"  ⚠️  Error importing member: {e}")
                    continue

            db.session.commit()
            print(f"  ✅ Imported {member_count} household members")

        # Import Recipes
        print("\n🍳 Importing recipes...")
        query = (
            "SELECT id, user_id, name, url, notes, household_id, visibility, created_at "
            "FROM recipes ORDER BY id;"
        )
        result = run_heroku_query(query)

        recipe_count = 0
        if result:
            lines = [
                l for l in result.split("\n") if "|" in l and not l.startswith("-")
            ]

            for line in lines[1:]:
                if not line.strip() or line.startswith("("):
                    continue

                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 4:
                    continue

                try:
                    # Skip if user_id is empty
                    if not parts[1]:
                        continue

                    recipe = Recipe(
                        id=int(parts[0]),
                        user_id=int(parts[1]),
                        name=parts[2],
                        url=parts[3] if parts[3] else "",
                    )

                    # Optional fields
                    if len(parts) > 4 and parts[4]:
                        recipe.notes = parts[4]
                    if len(parts) > 5 and parts[5]:
                        try:
                            recipe.household_id = int(parts[5])
                        except (ValueError, TypeError):
                            pass
                    if len(parts) > 6 and parts[6]:
                        recipe.visibility = parts[6]
                    if len(parts) > 7 and parts[7]:
                        # Parse the timestamp string to datetime object
                        from datetime import datetime

                        try:
                            recipe.created_at = datetime.fromisoformat(parts[7])
                        except (ValueError, TypeError):
                            pass

                    db.session.add(recipe)
                    recipe_count += 1
                except Exception as e:
                    print(f"  ⚠️  Error importing recipe: {e}")
                    continue

            db.session.commit()
            print(f"  ✅ Imported {recipe_count} recipes")

        # Import Recipe Ingredients
        print("\n🥕 Importing recipe ingredients...")
        query = (
            "SELECT id, recipe_id, ingredient_name, quantity, measurement "
            "FROM recipes_ingredients ORDER BY id;"
        )
        result = run_heroku_query(query)

        ingredient_count = 0
        if result:
            lines = [
                l for l in result.split("\n") if "|" in l and not l.startswith("-")
            ]

            for line in lines[1:]:
                if not line.strip() or line.startswith("("):
                    continue

                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 5:
                    continue

                try:
                    # Skip if recipe_id is empty
                    if not parts[1]:
                        continue

                    ingredient = RecipeIngredient(
                        id=int(parts[0]),
                        recipe_id=int(parts[1]),
                        ingredient_name=parts[2],
                    )

                    if parts[3]:
                        try:
                            ingredient.quantity = float(parts[3])
                        except (ValueError, TypeError):
                            pass
                    if parts[4]:
                        ingredient.measurement = parts[4]

                    db.session.add(ingredient)
                    ingredient_count += 1
                except Exception as e:
                    print(f"  ⚠️  Error importing ingredient: {e}")
                    continue

            db.session.commit()
            print(f"  ✅ Imported {ingredient_count} recipe ingredients")

        print("\n✅ Database import complete!")
        print("\nImported:")
        print(f"  - {user_count} users")
        print(f"  - {household_count} households")
        print(f"  - {member_count} household members")
        print(f"  - {recipe_count} recipes")
        print(f"  - {ingredient_count} recipe ingredients")
        print("\n💡 You can now login with your production credentials!")


if __name__ == "__main__":
    import_full_database()
