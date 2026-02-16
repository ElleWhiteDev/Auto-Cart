# Database Migration and Utility Scripts

This directory contains database migration scripts and utility tools for Auto-Cart.

## ⚠️ Important Notes

- **Backup your database** before running any migration scripts
- Test migrations on a development database first
- These scripts are for one-time migrations and administrative tasks
- Most scripts should only be run once

## Migration Scripts

### Multi-Household Migration
- `migrate_multi_household.py` - Migrates data to multi-household architecture
- `migrate_to_household.py` - Initial household migration
- `add_multi_cook_support.py` - Adds support for multiple cooks per meal

### Database Schema Updates
- `add_admin_fields.py` - Adds admin user fields
- `add_password_reset_fields.py` - Adds password reset functionality
- `add_custom_meal_field.py` - Adds custom meal support
- `add_meal_plan_email_preference.py` - Adds email preference fields
- `add_chef_assignment_email_preference.py` - Adds chef assignment email preferences
- `create_meal_plan_changes_table.py` - Creates meal plan change tracking table

### Bug Fixes
- `fix_meal_plan_nullable.py` - Fixes nullable constraints on meal plan fields
- `fix_oauth_column.py` - Fixes OAuth column issues

## Utility Scripts

### Administrative Tools
- `make_admin.py` - Promotes a user to admin status
- `reset_db_complete.py` - **DANGER**: Completely resets the database (development only)
- `send_daily_summaries.py` - Sends daily meal plan summary emails (for cron/scheduler)

### Heroku Deployment
- `migrate_heroku_db.py` - Migrates Heroku production database

## Usage

### Running a Migration Script

```bash
# Activate virtual environment
source venv/bin/activate

# Run the script
python scripts/script_name.py
```

### Making a User Admin

```bash
python scripts/make_admin.py
# Follow the prompts to enter username
```

### Sending Daily Summaries (Scheduled Task)

```bash
# Run manually
python scripts/send_daily_summaries.py

# Or set up with Heroku Scheduler
# Add this command to Heroku Scheduler: python send_daily_summaries.py
```

## Development Guidelines

### Creating New Migration Scripts

1. **Name clearly**: Use descriptive names like `add_feature_name.py`
2. **Add docstring**: Explain what the script does and when to use it
3. **Include rollback**: If possible, provide a way to undo changes
4. **Test first**: Always test on development database
5. **Document**: Add entry to this README

### Migration Script Template

```python
"""
Brief description of what this migration does.

Usage: python scripts/migration_name.py
"""

from app import app, db
from models import YourModel

def migrate():
    """Perform the migration."""
    with app.app_context():
        # Your migration code here
        db.session.commit()
        print("Migration completed successfully!")

if __name__ == '__main__':
    migrate()
```

## Safety Checklist

Before running any migration:

- [ ] Backup database
- [ ] Test on development database
- [ ] Review script code
- [ ] Understand what changes will be made
- [ ] Have rollback plan
- [ ] Run during low-traffic period (production)

## Questions?

See the main project README or open an issue on GitHub.

