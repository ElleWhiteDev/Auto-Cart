#!/usr/bin/env python3
"""
Create a test user to verify login functionality
"""

from app import app, db
from models import User

def create_test_user():
    """Create a test user"""
    
    with app.app_context():
        # Check if user already exists
        existing = User.query.filter(
            db.func.lower(User.username) == 'testuser'
        ).first()
        
        if existing:
            print(f"❌ User 'testuser' already exists (ID: {existing.id})")
            print(f"   Username: {existing.username}")
            print(f"   Email: {existing.email}")
            return
        
        # Create test user
        user = User.signup(
            username='TestUser',
            email='test@example.com',
            password='password123'
        )
        
        db.session.commit()
        
        print("✅ Test user created successfully!")
        print(f"   Username: {user.username}")
        print(f"   Email: {user.email}")
        print(f"   Password: password123")
        print("\nYou can now login with:")
        print("   - Username: TestUser (or testuser, TESTUSER, etc.)")
        print("   - Password: password123")

if __name__ == '__main__':
    create_test_user()

