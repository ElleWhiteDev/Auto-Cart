"""
Migration script to add password reset fields to users table.
Run this script to add reset_token and reset_token_expiry columns.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app import app, db
from models import User

def add_password_reset_fields():
    """Add password reset fields to users table"""
    with app.app_context():
        # Check if columns already exist
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('users')]

        if 'reset_token' in columns and 'reset_token_expiry' in columns:
            print("✓ Password reset fields already exist in users table")
            return

        print("Adding password reset fields to users table...")

        # Add columns using raw SQL
        # Note: SQLite doesn't support adding UNIQUE constraint in ALTER TABLE
        # The UNIQUE constraint will be enforced by the model definition
        with db.engine.connect() as conn:
            if 'reset_token' not in columns:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN reset_token TEXT"))
                print("✓ Added reset_token column")

            if 'reset_token_expiry' not in columns:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN reset_token_expiry TIMESTAMP"))
                print("✓ Added reset_token_expiry column")

            conn.commit()

        print("✓ Migration completed successfully!")

if __name__ == "__main__":
    add_password_reset_fields()
