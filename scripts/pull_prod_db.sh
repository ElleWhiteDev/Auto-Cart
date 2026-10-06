#!/bin/bash

echo "🔄 Pulling production database from Heroku to local..."
echo ""
echo "This will:"
echo "  1. Download the production database backup"
echo "  2. Convert it to SQLite format"
echo "  3. Replace your local database"
echo ""
echo "⚠️  WARNING: This will OVERWRITE your local database!"
echo ""

read -p "Continue? (yes/no): " response

if [ "$response" != "yes" ]; then
    echo "❌ Cancelled"
    exit 1
fi

echo ""
echo "📥 Downloading production database backup..."

# Download the latest backup
BACKUP_URL=$(heroku pg:backups:url --app auto-cart)
curl -o prod_backup.dump "$BACKUP_URL"

echo "✅ Downloaded backup"
echo ""
echo "📊 Restoring to local PostgreSQL database..."

# Create local database
dropdb autocart_local 2>/dev/null || true
createdb autocart_local

# Restore the backup
pg_restore --verbose --clean --no-acl --no-owner -d autocart_local prod_backup.dump

echo ""
echo "✅ Production database restored to local PostgreSQL!"
echo ""
echo "📝 Updating app configuration to use local PostgreSQL..."

# Update .env or create it
if [ ! -f .env ]; then
    echo "Creating .env file..."
    echo "DATABASE_URL=postgresql://localhost/autocart_local" > .env
else
    # Check if DATABASE_URL exists in .env
    if grep -q "DATABASE_URL" .env; then
        # Comment out old DATABASE_URL and add new one
        sed -i.bak 's/^DATABASE_URL=/#DATABASE_URL=/' .env
        echo "DATABASE_URL=postgresql://localhost/autocart_local" >> .env
    else
        echo "DATABASE_URL=postgresql://localhost/autocart_local" >> .env
    fi
fi

echo "✅ Configuration updated!"
echo ""
echo "🎉 Done! Your local database now has all production data."
echo ""
echo "To use it, make sure your app reads from DATABASE_URL in .env"
echo "You can now login with your production credentials!"

