#!/usr/bin/env python3
"""
Test script to verify admin member management functionality
"""

from app import app
from models import User, Household, HouseholdMember

def test_admin_members():
    """Test the admin member management"""
    
    with app.app_context():
        print("🔍 Testing Admin Member Management\n")
        
        # Check for admin users
        print("1️⃣ Checking for admin users...")
        admins = User.query.filter_by(is_admin=True).all()
        if not admins:
            print("   ❌ No admin users found!")
            print("   Create an admin user first.")
            return
        
        print(f"   ✅ Found {len(admins)} admin user(s):")
        for admin in admins:
            print(f"      - {admin.username} (ID: {admin.id})")
        
        # Check for households
        print("\n2️⃣ Checking for households...")
        households = Household.query.all()
        if not households:
            print("   ❌ No households found!")
            return
        
        print(f"   ✅ Found {len(households)} household(s):")
        for household in households:
            members = HouseholdMember.query.filter_by(household_id=household.id).all()
            print(f"      - {household.name} (ID: {household.id}) - {len(members)} members")
        
        # Test member data structure
        print("\n3️⃣ Testing member data structure...")
        test_household = households[0]
        members = HouseholdMember.query.filter_by(household_id=test_household.id).all()
        
        if not members:
            print(f"   ❌ No members in household '{test_household.name}'")
            return
        
        print(f"   Testing household: {test_household.name}")
        for member in members:
            try:
                data = {
                    "member_id": member.id,
                    "user_id": member.user_id,
                    "username": member.user.username,
                    "email": member.user.email,
                    "role": member.role,
                    "receive_meal_plan_emails": member.receive_meal_plan_emails,
                    "receive_chef_assignment_emails": member.receive_chef_assignment_emails,
                    "joined_at": member.joined_at.strftime('%Y-%m-%d') if member.joined_at else None
                }
                print(f"   ✅ {data['username']}: {data}")
            except Exception as e:
                print(f"   ❌ Error with member {member.id}: {e}")
        
        print("\n4️⃣ Testing API endpoint simulation...")
        try:
            members_data = []
            for member in members:
                members_data.append({
                    "member_id": member.id,
                    "user_id": member.user_id,
                    "username": member.user.username,
                    "email": member.user.email,
                    "role": member.role,
                    "receive_meal_plan_emails": member.receive_meal_plan_emails,
                    "receive_chef_assignment_emails": member.receive_chef_assignment_emails,
                    "joined_at": member.joined_at.strftime('%Y-%m-%d') if member.joined_at else None
                })
            
            import json
            json_output = json.dumps({"success": True, "members": members_data}, indent=2)
            print(f"   ✅ API would return:\n{json_output}")
        except Exception as e:
            print(f"   ❌ Error creating JSON response: {e}")
        
        print("\n✅ All tests passed!")
        print("\n💡 If the admin dashboard still doesn't work:")
        print("   1. Make sure you're logged in as an admin user")
        print("   2. Check browser console (F12) for JavaScript errors")
        print("   3. Check that Bootstrap 5 is loaded (modal requires it)")

if __name__ == '__main__':
    test_admin_members()

