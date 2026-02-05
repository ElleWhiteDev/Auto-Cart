"""Make a user an admin"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app import app
from models import db, User

def make_admin(username):
    """Make a user an admin by username"""
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        
        if not user:
            print(f"✗ User '{username}' not found")
            return False
        
        if user.is_admin:
            print(f"✓ User '{username}' is already an admin")
            return True
        
        user.is_admin = True
        db.session.commit()
        print(f"✓ User '{username}' is now an admin!")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <username>")
        print("\nExample: python make_admin.py Elle")
        sys.exit(1)
    
    username = sys.argv[1]
    make_admin(username)

