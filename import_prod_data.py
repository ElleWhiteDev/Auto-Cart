#!/usr/bin/env python3
"""
Import production user data from Heroku to local SQLite database
"""

import os
import subprocess
from app import app, db
from models import User

def import_users_from_heroku():
    """Import users from Heroku production database"""

    print("🔄 Importing users from Heroku production database...")
    print()

    # Query Heroku database for users
    result = subprocess.run(
        ['heroku', 'pg:psql', '--app', 'auto-cart', '-c',
         'SELECT id, username, email, password, is_admin, '
         'alexa_access_token, alexa_default_grocery_list_id FROM users ORDER BY id;'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"❌ Error querying Heroku database: {result.stderr}")
        return

    print("Production database query result:")
    print(result.stdout)
    print()

    # Parse the output (this is a simple parser for psql output)
    lines = result.stdout.strip().split('\n')

    # Find the data rows (skip header and separator lines)
    data_started = False
    users_data = []

    for line in lines:
        if '----+' in line:
            data_started = True
            continue
        if data_started and line.strip() and not line.startswith('(') and '|' in line:
            users_data.append(line)

    if not users_data:
        print("❌ No user data found in production database")
        return

    print(f"Found {len(users_data)} users in production")
    print()

    with app.app_context():
        # Clear existing users (optional - comment out if you want to keep local users)
        print("⚠️  Clearing existing local users...")
        User.query.delete()
        db.session.commit()

        imported_count = 0

        for line in users_data:
            # Parse the line (format: id | username | email | password | ...)
            parts = [p.strip() for p in line.split('|')]

            if len(parts) < 4:
                continue

            try:
                user_id = int(parts[0])
                username = parts[1]
                email = parts[2]
                password_hash = parts[3]
                is_admin = parts[4] == 't' if len(parts) > 4 else False

                # Create user directly (bypass signup to preserve password hash)
                user = User(
                    id=user_id,
                    username=username,
                    email=email,
                    password=password_hash,
                    is_admin=is_admin
                )

                # Set optional fields if present
                if len(parts) > 5 and parts[5]:
                    user.alexa_access_token = parts[5]
                if len(parts) > 6 and parts[6]:
                    try:
                        user.alexa_default_grocery_list_id = int(parts[6])
                    except (ValueError, TypeError):
                        pass

                db.session.add(user)
                imported_count += 1

                print(f"✅ Imported: {username} ({email})")

            except Exception as e:
                print(f"❌ Error importing user from line: {line}")
                print(f"   Error: {e}")
                continue

        db.session.commit()

        print()
        print(f"✅ Successfully imported {imported_count} users to local database!")
        print()
        print("You can now login locally with your production credentials:")
        print("  - Username: Elle (or elle, ELLE, etc.)")
        print("  - Password: <your production password>")

if __name__ == '__main__':
    import_users_from_heroku()
