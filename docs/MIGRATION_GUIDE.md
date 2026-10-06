# Database Migration Guide

This project now uses **Flask-Migrate** (Alembic) for database version control.

## What is Flask-Migrate?

Flask-Migrate provides database migration support for SQLAlchemy. It allows you to:
- Track database schema changes over time
- Apply changes incrementally
- Roll back changes if needed
- Keep development, staging, and production databases in sync

## Common Commands

### Creating a New Migration

When you make changes to your models (add/remove/modify columns, tables, etc.):

```bash
# Activate virtual environment
source venv/bin/activate

# Generate a new migration
flask db migrate -m "Description of changes"

# Review the generated migration file in migrations/versions/
# Edit if necessary to handle data migrations or complex changes

# Apply the migration
flask db upgrade
```

### Viewing Migration Status

```bash
# Show current migration version
flask db current

# Show migration history
flask db history

# Show pending migrations
flask db heads
```

### Rolling Back Migrations

```bash
# Downgrade one version
flask db downgrade

# Downgrade to a specific version
flask db downgrade <revision_id>

# Downgrade all the way to the beginning
flask db downgrade base
```

### Other Useful Commands

```bash
# Show SQL that would be executed (without running it)
flask db upgrade --sql

# Mark database at specific version without running migrations
flask db stamp <revision_id>

# Mark database at latest version
flask db stamp head
```

## Migration Workflow

### Development

1. Make changes to your models in `models.py`
2. Generate migration: `flask db migrate -m "Add user avatar field"`
3. Review the generated migration file
4. Apply migration: `flask db upgrade`
5. Test your changes
6. Commit both the model changes AND the migration file to git

### Production Deployment

1. Pull latest code (includes new migration files)
2. Backup your database first!
3. Run migrations: `flask db upgrade`
4. Restart your application

## Current Status

- ✅ Migration system initialized
- ✅ Initial migration created (7379da7f5251)
- ✅ Database stamped at current version
- ✅ Ready for future schema changes

## Initial Migration Notes

The initial migration (`7379da7f5251_initial_migration_existing_schema.py`) was created from the existing database schema. It includes:

- Cleanup of legacy table `grocery_lists_recipe_ingredients` (no longer used)
- All current tables are tracked

## Best Practices

1. **Always review generated migrations** - Alembic does its best but may need manual adjustments
2. **Test migrations on development first** - Never run untested migrations in production
3. **Backup before migrating** - Always backup production databases before applying migrations
4. **One logical change per migration** - Makes it easier to understand and roll back if needed
5. **Descriptive migration messages** - Use clear, concise descriptions
6. **Commit migrations with code** - Migration files should be version controlled

## Handling Data Migrations

Sometimes you need to migrate data, not just schema. Example:

```python
def upgrade():
    # Add new column
    op.add_column('users', sa.Column('full_name', sa.String(200)))
    
    # Migrate data
    connection = op.get_bind()
    connection.execute(
        "UPDATE users SET full_name = first_name || ' ' || last_name"
    )
    
    # Drop old columns
    op.drop_column('users', 'first_name')
    op.drop_column('users', 'last_name')
```

## Troubleshooting

### Migration conflicts
If multiple developers create migrations simultaneously, you may need to merge them:
```bash
flask db merge <revision1> <revision2>
```

### Circular dependencies warning
If you see warnings about circular foreign key dependencies, you may need to manually adjust the migration to use `use_alter=True` on foreign keys.

### Migration fails
1. Check the error message
2. Review the migration file
3. If needed, downgrade and fix the migration
4. Re-run the upgrade

## Resources

- [Flask-Migrate Documentation](https://flask-migrate.readthedocs.io/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)

