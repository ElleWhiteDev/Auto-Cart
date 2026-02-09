"""
Migration script to create the meal_plan_changes table for tracking meal plan changes.
Run this script once to create the table.
"""

from app import create_app
from models import db

# create_app returns a tuple, we only need the first element (the app)
app, bcrypt, mail, kroger_service, kroger_session_manager, kroger_workflow = create_app()

with app.app_context():
    # Create the meal_plan_changes table using SQLAlchemy
    # This will use db.create_all() which is safer than raw SQL
    print("Creating meal_plan_changes table...")

    try:
        db.create_all()
        print("✓ meal_plan_changes table created successfully!")
        print("✓ All database tables are up to date!")
    except Exception as e:
        print(f"Error creating table: {e}")
        print("The table may already exist, which is fine.")
