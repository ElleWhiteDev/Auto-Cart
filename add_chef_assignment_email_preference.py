"""
Migration script to add receive_chef_assignment_emails field to household_members table.
Run this script to add the chef assignment email notification preference column.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app import app, db
from models import HouseholdMember

def add_chef_assignment_email_preference():
    """Add receive_chef_assignment_emails field to household_members table"""
    with app.app_context():
        # Check if column already exists
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('household_members')]

        if 'receive_chef_assignment_emails' in columns:
            print("✓ receive_chef_assignment_emails field already exists in household_members table")
            return

        print("Adding receive_chef_assignment_emails field to household_members table...")

        # Add column using raw SQL with default value of True (1 for SQLite)
        with db.engine.connect() as conn:
            conn.execute(db.text(
                "ALTER TABLE household_members ADD COLUMN receive_chef_assignment_emails BOOLEAN NOT NULL DEFAULT 1"
            ))
            conn.commit()
            print("✓ Added receive_chef_assignment_emails column (default: True)")

        print("✓ Migration completed successfully!")
        print("All existing household members will receive chef assignment emails by default.")

if __name__ == "__main__":
    add_chef_assignment_email_preference()

