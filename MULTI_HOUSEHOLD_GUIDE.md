# Multi-Household Support Guide

## Overview

Auto-Cart now supports **multiple households per profile**. This means:

- ✅ A profile (user) can be part of **multiple households**
- ✅ A profile can be an **owner** of one or more households
- ✅ A profile can be a **member** of one or more households
- ✅ All **recipes** and **grocery lists** are scoped to households
- ✅ Users can easily **switch** between their households

## Key Concepts

### Profiles (Users)
A profile represents a single user account in the system. Each profile has:
- Unique username and email
- Password for authentication
- Optional Kroger integration (profile_id, oauth_token, refresh_token)

### Households
A household is a group of profiles that collaborate on:
- Recipe collections
- Grocery lists
- Meal planning
- Shopping activities

### Household Membership
The relationship between profiles and households is managed through the `HouseholdMember` model:
- **Owner**: Can manage household settings, invite/remove members, set Kroger account
- **Member**: Can view and contribute to household recipes and lists

## Data Model

### Database Schema

```
User (Profile)
├── id
├── username
├── email
├── password
├── profile_id (Kroger)
└── household_memberships → [HouseholdMember]

HouseholdMember
├── id
├── household_id → Household
├── user_id → User
├── role ('owner' or 'member')
└── joined_at

Household
├── id
├── name
├── kroger_user_id → User
├── members → [HouseholdMember]
├── recipes → [Recipe]
├── grocery_lists → [GroceryList]
└── meal_plan_entries → [MealPlanEntry]

Recipe
├── id
├── user_id → User (creator)
├── household_id → Household (required)
├── name
├── ingredients
└── visibility

GroceryList
├── id
├── household_id → Household (required)
├── created_by_user_id → User
├── items
└── status
```

## Usage Examples

### Creating Multiple Households

A user can create multiple households:

```python
# User creates their first household
household1 = Household(name="Smith Family")
membership1 = HouseholdMember(
    household_id=household1.id,
    user_id=user.id,
    role='owner'
)

# Same user creates a second household
household2 = Household(name="Roommates Apartment")
membership2 = HouseholdMember(
    household_id=household2.id,
    user_id=user.id,
    role='owner'
)
```

### Joining Multiple Households

A user can be invited to join other households:

```python
# User joins another household as a member
membership3 = HouseholdMember(
    household_id=other_household.id,
    user_id=user.id,
    role='member'
)
```

### Accessing User's Households

```python
# Get all households a user belongs to
user.get_households()  # Returns list of all households

# Get only owned households
user.get_owned_households()  # Returns households where user is owner

# Get only member households
user.get_member_households()  # Returns households where user is regular member
```

### Checking Permissions

```python
# Check if user is owner of a household
household.is_user_owner(user.id)  # Returns True/False

# Check if user is member (owner or regular)
household.is_user_member(user.id)  # Returns True/False

# Check membership role
membership.is_owner()  # Returns True if role is 'owner'
membership.is_member()  # Returns True if role is 'member'
```

## UI Features

### Household Switching
Users can switch between their households from the **Household Settings** page:
1. Navigate to Household Settings (click household name in nav)
2. View "My Households" section (shows all households you belong to)
3. Click "Switch" button to change active household

### Creating New Households
Users can create additional households at any time:
1. Go to Household Settings
2. Click "Create New Household" button
3. Enter household name and submit

### Managing Members
Household owners can:
- Invite users by username
- Remove members from the household
- See member roles (Owner/Member)

## Migration

To ensure your database supports multi-household features, run:

```bash
python migrate_multi_household.py
```

This script will:
- Verify all required tables exist
- Check household_members constraints
- Update any 'admin' roles to 'owner' for consistency
- Display statistics about multi-household usage

## API Reference

### User Model Methods

- `get_households()` - Get all households user belongs to
- `get_owned_households()` - Get households where user is owner
- `get_member_households()` - Get households where user is regular member

### Household Model Methods

- `get_owners()` - Get all owner members
- `get_regular_members()` - Get all non-owner members
- `is_user_owner(user_id)` - Check if user is owner
- `is_user_member(user_id)` - Check if user is member

### HouseholdMember Model Methods

- `is_owner()` - Check if membership has owner privileges
- `is_member()` - Check if membership is regular member

## Best Practices

1. **Always scope recipes and lists to households** - Never create recipes or lists without a household_id
2. **Use helper methods for permission checks** - Use `is_owner()` instead of checking `role == 'owner'`
3. **Verify household membership** - Always check user is member before allowing access to household data
4. **Handle household switching gracefully** - Clear grocery list session when switching households

## Notes

- Recipes and grocery lists are **always** scoped to a household
- Users see recipes from their currently active household
- Switching households changes which recipes and lists are visible
- Each household can have its own Kroger integration account

