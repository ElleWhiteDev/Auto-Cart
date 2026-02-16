"""
Migration script to add multi-cook support to meal plan entries.
This creates the meal_plan_cooks association table for many-to-many relationships.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import app
from models import db
from sqlalchemy import text


def add_multi_cook_support():
    """Add meal_plan_cooks table for multi-cook support"""
    with app.app_context():
        try:
            print("Starting multi-cook support migration...")

            # Check if table already exists
            try:
                db.session.execute(
                    text("SELECT * FROM meal_plan_cooks LIMIT 1")
                )
                print("✓ meal_plan_cooks table already exists")
                db.session.commit()
                return
            except Exception:
                db.session.rollback()
                print("Creating meal_plan_cooks table...")

            # Create the meal_plan_cooks association table
            db.session.execute(
                text("""
                    CREATE TABLE meal_plan_cooks (
                        meal_plan_entry_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        PRIMARY KEY (meal_plan_entry_id, user_id),
                        FOREIGN KEY (meal_plan_entry_id) REFERENCES meal_plan_entries(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
            )
            print("✓ Created meal_plan_cooks table")

            # Migrate existing single cook assignments to the new table
            print("Migrating existing cook assignments...")
            result = db.session.execute(
                text("""
                    INSERT INTO meal_plan_cooks (meal_plan_entry_id, user_id)
                    SELECT id, assigned_cook_user_id
                    FROM meal_plan_entries
                    WHERE assigned_cook_user_id IS NOT NULL
                """)
            )
            print(f"✓ Migrated {result.rowcount} existing cook assignments")

            db.session.commit()
            print("✅ Multi-cook support migration completed successfully!")

        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during migration: {e}")
            raise


if __name__ == "__main__":
    add_multi_cook_support()

