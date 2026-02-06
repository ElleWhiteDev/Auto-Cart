# Multi-Household Support - Changes Summary

## Overview
Updated Auto-Cart to fully support profiles being part of multiple households, with the ability to own and be members of different households. All recipes and lists remain scoped to households.

## Latest Updates (Household Settings Reorganization & Enhanced Invitations)

### New Features Added:
1. **Edit Household Name** - Owners can now edit the household name directly from settings
2. **Enhanced Member Information** - Member table now shows email, last login, and role
3. **Reorganized Settings Page** - Sections now in logical order: My Households → Household Info → House Members → Kroger Integration
4. **Improved UI** - Cleaner layout with better information display
5. **Smart Invitations** - Invite by username OR email
6. **Email Invitations for New Users** - Automatically sends invitation emails to non-registered users with:
   - App introduction and feature overview
   - Registration link with household join instructions
   - Explanation of what households are
   - Mobile app installation instructions
   - Inviter information
   - Admin contact for support
7. **Welcome Email for Added Members** - When users are added to a household, they receive:
   - Welcome email explaining household benefits
   - Information about which household they joined
   - Instructions on creating their own households
   - Link to household settings
8. **Delete Household** - Owners can permanently delete households with:
   - Cascade deletion of all recipes, grocery lists, and meal plans
   - Double confirmation prompt requiring household name
   - Automatic switch to another household if available
   - Comprehensive logging of deleted data
   - "Danger Zone" section with clear warnings
9. **Processing States on All Action Buttons** - Shows loading spinners when:
   - Inviting members
   - Editing household name
   - Removing members
   - Deleting household
10. **Branded Email Templates** - Updated email design with:
    - Primary blue (#004c91) gradient headers
    - Orange accent (#ff6600) for highlights
    - SVG logo embedded inline
    - Professional, on-brand styling
    - White button text for proper contrast

## Files Modified

### 1. `models.py`
**Changes:**
- Updated `Household` model docstring to clarify multi-household support
- Added helper methods to `Household`:
  - `get_owners()` - Get all owner members
  - `get_regular_members()` - Get all non-owner members
  - `is_user_owner(user_id)` - Check if user is owner
  - `is_user_member(user_id)` - Check if user is member

- Updated `HouseholdMember` model docstring to clarify roles
- Updated role comment from `'admin' or 'member'` to `'owner' or 'member'`
- Added helper methods to `HouseholdMember`:
  - `is_owner()` - Check if membership has owner privileges
  - `is_member()` - Check if membership is regular member

- Updated `User` model docstring to clarify multi-household support
- Added helper methods to `User`:
  - `get_households()` - Get all households user belongs to
  - `get_owned_households()` - Get households where user is owner
  - `get_member_households()` - Get households where user is regular member

- Updated `Recipe` model docstring to clarify household scoping
- Updated `GroceryList` model docstring to clarify household scoping

### 2. `app.py`
**New Routes and Functions:**
- Updated `household_settings()` route:
  - Added `user_households` to template context
  - Changed `is_owner=(g.household_member.role == 'owner')` to `is_owner=g.household_member.is_owner()`

- **NEW: Added `edit_household_name()` route:**
  - POST route at `/household/edit-name`
  - Allows owners to edit household name
  - Validates ownership and name input
  - Provides success feedback

- **ENHANCED: `invite_household_member()` route:**
  - Now accepts **username OR email** as identifier
  - Searches for existing users by both username and email
  - **NEW: Email invitation for non-existing users**
    - Detects email addresses (contains '@')
    - Sends beautifully formatted HTML invitation email
    - Includes app introduction and feature overview
    - Provides registration link
    - Shows inviter name and email
    - Includes mobile app installation instructions
    - Admin contact in footer for support
  - Provides appropriate feedback for each scenario

- **NEW: Added `send_household_invitation_email()` function:**
  - Sends HTML and plain text invitation emails
  - **Professional branded email template** with:
    - **Primary blue gradient header** (#004c91 to #1e6bb8)
    - **SVG logo** embedded inline (shopping cart icon)
    - **Orange accent colors** (#ff6600) for highlights
    - Blue borders on feature boxes
    - Orange borders on mobile instructions
  - Includes:
    - Inviter information (name and email)
    - Household name
    - App feature overview
    - Registration instructions
    - Mobile app installation guide (iOS and Android)
    - Admin support email in footer
  - Uses Flask-Mail for delivery

- Updated permission checks to use helper methods:
  - `invite_household_member()`: Changed `g.household_member.role != 'owner'` to `not g.household_member.is_owner()`
  - `remove_household_member()`: Changed `g.household_member.role != 'owner'` to `not g.household_member.is_owner()`
  - `set_kroger_user()`: Changed `g.household_member.role != 'owner'` to `not g.household_member.is_owner()`

### 3. `templates/household_settings.html`
**Major Reorganization:**
- **REORGANIZED** entire page structure with new section order:
  1. **My Households** - Switch between households and create new ones
  2. **Household Info** - View and edit household details
  3. **House Members** - Enhanced member table with detailed information
  4. **Kroger Integration** - Manage Kroger account settings

**Section Details:**

- **My Households Section:**
  - Always visible (not just for multi-household users)
  - Shows all households user belongs to
  - Displays household name, current indicator, role badge
  - Switch button for non-current households
  - "Create New Household" button always visible

- **Household Info Section (NEW):**
  - Shows household name, created date, member count, user role
  - **Edit household name form** (owners only) - inline editing capability

- **House Members Section (ENHANCED):**
  - **Table format** showing: Username, Email, Role, Last Login
  - **Smaller remove button** - icon only, more compact (0.1rem padding, 0.65rem font)
  - **Enhanced invite form** - accepts username OR email with `id="invite-form"` and `id="invite-btn"`
  - **Processing state on submit** - JavaScript disables button and shows spinner with "Sending..." text
  - **Updated help text** - explains email invitation feature for non-registered users

- **Kroger Integration Section:**
  - Moved to bottom of page for better organization
  - Shows connection status and account selection

### 4. New Files Created

#### `migrate_multi_household.py`
Migration script that:
- Verifies all required tables exist
- Checks household_members table structure
- Updates any 'admin' roles to 'owner' for consistency
- Verifies recipes are scoped to households
- Verifies grocery lists are scoped to households
- Displays multi-household statistics

#### `MULTI_HOUSEHOLD_GUIDE.md`
Comprehensive documentation covering:
- Overview of multi-household support
- Key concepts (Profiles, Households, Membership)
- Database schema
- Usage examples
- UI features
- Migration instructions
- API reference
- Best practices

#### `CHANGES_SUMMARY.md`
This file - summary of all changes made

## Key Features Implemented

### 1. Multiple Household Membership
- Users can now be members of multiple households simultaneously
- Each membership has a role (owner or member)
- Users can switch between households via the UI

### 2. Multiple Household Ownership
- Users can own multiple households
- Ownership grants permission to manage household settings and members
- No limit on number of households a user can own

### 3. Helper Methods for Cleaner Code
- Added semantic methods to check roles and permissions
- Replaced direct role string comparisons with method calls
- Improved code readability and maintainability

### 4. Enhanced UI
- Household settings page now shows all user's households
- Easy switching between households
- Clear indication of current household and user's role
- Ability to create new households from settings page

### 5. Data Scoping
- All recipes remain scoped to households
- All grocery lists remain scoped to households
- Users only see data from their currently active household

## Database Schema

No schema changes were required - the existing structure already supported multiple households per user through the `household_members` junction table. The changes were primarily:
- Code improvements (helper methods)
- UI enhancements (household switching)
- Documentation updates
- Role terminology consistency ('owner' instead of 'admin')

## Testing

Run the migration script to verify:
```bash
source venv/bin/activate
python migrate_multi_household.py
```

Expected output:
- ✓ All tables verified/created
- ✓ Role values verified
- ✓ All recipes scoped to households
- ✓ All grocery lists scoped to households
- Statistics showing household distribution

## Backward Compatibility

All changes are backward compatible:
- Existing single-household users continue to work normally
- No data migration required
- Existing 'owner' roles work as before
- UI gracefully handles single vs. multiple households

## Next Steps

Users can now:
1. Create multiple households from the household settings page
2. Join other households by username
3. Switch between households to access different recipe collections
4. Manage each household independently
5. Be an owner of some households and member of others
