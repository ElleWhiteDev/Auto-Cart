"""Add custom_meal_name field to meal_plan_entries table"""
import os
from dotenv import load_dotenv

load_dotenv()

from app import app
from models import db

def add_custom_meal_field():
    """Add custom_meal_name field and make recipe_id nullable"""
    with app.app_context():
        try:
            from sqlalchemy import text

            # Add custom_meal_name column
            db.session.execute(text('ALTER TABLE meal_plan_entries ADD COLUMN custom_meal_name VARCHAR(200)'))
            print("   ✓ Added custom_meal_name column")

            db.session.commit()
            print("✓ Migration completed successfully!")

        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("✓ Column already exists, skipping migration")
            else:
                print(f"Error: {e}")
            db.session.rollback()

if __name__ == '__main__':
    print("Adding custom meal field to meal_plan_entries table...")
    add_custom_meal_field()
