"""Add admin fields to users table"""
import os
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from app import app
from models import db

def add_admin_fields():
    """Add is_admin and last_activity fields to users table"""
    with app.app_context():
        print("Adding admin fields to users table...")
        
        try:
            # Add is_admin column
            db.session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
            print("   ✓ Added is_admin column")
        except Exception as e:
            print(f"   - is_admin column already exists or error: {e}")
        
        try:
            # Add last_activity column
            db.session.execute(text("ALTER TABLE users ADD COLUMN last_activity DATETIME"))
            print("   ✓ Added last_activity column")
        except Exception as e:
            print(f"   - last_activity column already exists or error: {e}")
        
        try:
            db.session.commit()
            print("✓ Migration completed successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"✗ Migration failed: {e}")

if __name__ == '__main__':
    add_admin_fields()

