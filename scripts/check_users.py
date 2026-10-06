#!/usr/bin/env python3
"""
Quick script to check users in the database
"""

from app import app, db
from models import User

def check_users():
    """Display all users in the database"""
    
    with app.app_context():
        users = User.query.all()
        
        if not users:
            print("❌ No users found in database!")
            print("\nDatabase location:", app.config.get('SQLALCHEMY_DATABASE_URI'))
            return
        
        print(f"✅ Found {len(users)} user(s) in database:")
        print("\nDatabase location:", app.config.get('SQLALCHEMY_DATABASE_URI'))
        print("\n" + "="*80)
        
        for user in users:
            print(f"\nUser ID: {user.id}")
            print(f"Username: '{user.username}'")
            print(f"Email: '{user.email}'")
            print(f"Password Hash: {user.password[:20]}... (truncated)")
            print(f"Is Admin: {user.is_admin}")
            print("-"*80)

if __name__ == '__main__':
    check_users()

