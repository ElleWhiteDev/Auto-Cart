"""Make recipe_id nullable in meal_plan_entries table"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import app
from models import db


def fix_meal_plan_nullable():
    """Make recipe_id nullable by recreating the table"""
    with app.app_context():
        try:
            from sqlalchemy import text

            print("Making recipe_id nullable in meal_plan_entries...")

            # Create new table with nullable recipe_id
            db.session.execute(
                text("""
                CREATE TABLE meal_plan_entries_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_id INTEGER NOT NULL,
                    recipe_id INTEGER,
                    custom_meal_name VARCHAR(200),
                    date DATE NOT NULL,
                    meal_type VARCHAR(20),
                    assigned_cook_user_id INTEGER,
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (household_id) REFERENCES households(id) ON DELETE CASCADE,
                    FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                    FOREIGN KEY (assigned_cook_user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            )
            print("   ✓ Created new table structure")

            # Copy data from old table (specify columns to handle any schema differences)
            db.session.execute(
                text("""
                INSERT INTO meal_plan_entries_new
                (id, household_id, recipe_id, custom_meal_name, date, meal_type, assigned_cook_user_id, notes, created_at)
                SELECT id, household_id, recipe_id, custom_meal_name, date, meal_type, assigned_cook_user_id, notes, created_at
                FROM meal_plan_entries
            """)
            )
            print("   ✓ Copied existing data")

            # Drop old table
            db.session.execute(text("DROP TABLE meal_plan_entries"))
            print("   ✓ Dropped old table")

            # Rename new table
            db.session.execute(
                text("ALTER TABLE meal_plan_entries_new RENAME TO meal_plan_entries")
            )
            print("   ✓ Renamed new table")

            db.session.commit()
            print("✓ Migration completed successfully!")

        except Exception as e:
            print(f"Error: {e}")
            db.session.rollback()
            raise


if __name__ == "__main__":
    print("Fixing meal_plan_entries table to allow custom meals...")
    fix_meal_plan_nullable()
