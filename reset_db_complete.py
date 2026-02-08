import os
from app import app, db

# Stop the Flask app first, then run this script

# Delete the existing database file
db_files = ["app.db", "instance/app.db"]
for db_file in db_files:
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"Deleted {db_file}")

# Clear SQLAlchemy metadata cache
with app.app_context():
    db.metadata.clear()
    db.drop_all()  # This ensures clean slate
    db.create_all()
    print("Recreated database with fresh schema")
