#!/usr/bin/env python3
"""
Add email preference columns to household_members table if they don't exist.
This fixes the admin manage members functionality.
"""

from app import app, db
from sqlalchemy import text

def add_email_preference_columns():
    """Add receive_meal_plan_emails and receive_chef_assignment_emails columns"""
    
    print("🔧 Checking household_members table for email preference columns...")
    
    with app.app_context():
        try:
            # Check if columns exist
            result = db.session.execute(text("PRAGMA table_info(household_members)"))
            columns = [row[1] for row in result]
            
            print(f"📊 Current columns: {columns}")
            
            needs_meal_plan_column = 'receive_meal_plan_emails' not in columns
            needs_chef_column = 'receive_chef_assignment_emails' not in columns
            
            if not needs_meal_plan_column and not needs_chef_column:
                print("✅ Both email preference columns already exist!")
                print("No migration needed.")
                return
            
            # Add missing columns
            if needs_meal_plan_column:
                print("➕ Adding receive_meal_plan_emails column...")
                db.session.execute(text(
                    "ALTER TABLE household_members ADD COLUMN receive_meal_plan_emails BOOLEAN NOT NULL DEFAULT 1"
                ))
                print("✅ Added receive_meal_plan_emails column")
            
            if needs_chef_column:
                print("➕ Adding receive_chef_assignment_emails column...")
                db.session.execute(text(
                    "ALTER TABLE household_members ADD COLUMN receive_chef_assignment_emails BOOLEAN NOT NULL DEFAULT 1"
                ))
                print("✅ Added receive_chef_assignment_emails column")
            
            db.session.commit()
            
            print("\n🎉 Migration complete!")
            print("Admin manage members functionality should now work correctly.")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error during migration: {e}")
            print("\nPlease check:")
            print("1. The database file exists and is accessible")
            print("2. You have write permissions")
            raise

if __name__ == '__main__':
    add_email_preference_columns()

