#!/usr/bin/env python3
"""
Migration script to rename oath_token to oauth_token in the users table.
This fixes the typo that was corrected in the models.
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
database_url = os.environ.get('DATABASE_URL')

if not database_url:
    print("❌ ERROR: DATABASE_URL not found in environment variables")
    print("Please set DATABASE_URL in your .env file")
    exit(1)

# Fix Heroku postgres:// URL to postgresql://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

print(f"🔧 Connecting to database...")

try:
    # Create engine
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        # Check if oath_token column exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('oath_token', 'oauth_token')
        """))
        
        columns = [row[0] for row in result]
        
        print(f"📊 Found columns: {columns}")
        
        if 'oath_token' in columns and 'oauth_token' not in columns:
            print("🔄 Renaming oath_token to oauth_token...")
            conn.execute(text("""
                ALTER TABLE users 
                RENAME COLUMN oath_token TO oauth_token
            """))
            conn.commit()
            print("✅ Column renamed successfully!")
            
        elif 'oauth_token' in columns and 'oath_token' not in columns:
            print("✅ Column already named correctly (oauth_token)")
            
        elif 'oath_token' in columns and 'oauth_token' in columns:
            print("⚠️  Both columns exist! Merging data...")
            # Copy data from oath_token to oauth_token if oauth_token is null
            conn.execute(text("""
                UPDATE users 
                SET oauth_token = oath_token 
                WHERE oauth_token IS NULL AND oath_token IS NOT NULL
            """))
            # Drop the old column
            conn.execute(text("ALTER TABLE users DROP COLUMN oath_token"))
            conn.commit()
            print("✅ Merged and cleaned up columns!")
            
        else:
            print("❌ Neither column found! Database schema may be different.")
            print("Creating oauth_token column...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN oauth_token TEXT
            """))
            conn.commit()
            print("✅ Column created!")
    
    print("\n🎉 Migration completed successfully!")
    print("You can now run the app with: python app.py")
    
except Exception as e:
    print(f"\n❌ Error during migration: {e}")
    print("\nIf you're using SQLite, you may need to recreate the database.")
    print("For PostgreSQL, make sure the database is running and accessible.")
    exit(1)

