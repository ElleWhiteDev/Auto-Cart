"""
Auto-Cart Flask Application.

A grocery list and meal planning application with Kroger integration.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, session, g, request, render_template, flash, redirect, url_for
from flask_mail import Mail
from logging_config import logger

from models import User, Household, HouseholdMember, GroceryList
from app_config import config
from utils import CURR_USER_KEY, CURR_GROCERY_LIST_KEY, get_est_now
from kroger import KrogerAPIService, KrogerSessionManager, KrogerWorkflow

# Import extensions
from extensions import (
    init_extensions,
    db,
    bcrypt,
    mail as mail_ext,
    migrate,
    socketio,
    cache,
    limiter,
    talisman,
)

# Import blueprints
from routes import register_blueprints
from alexa_api import alexa_bp


def create_app(config_name=None):
    """
    Create and configure the Flask application.

    Args:
        config_name: Configuration name (development, production, testing)

    Returns:
        Flask application instance
    """
    app = Flask(__name__)

    # Determine config
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    if config_name == "production":
        config_name = "production"

    app.config.from_object(config[config_name])

    # Initialize all Flask extensions (including database)
    init_extensions(app)

    # Database tables are managed by Flask-Migrate
    # Use 'flask db upgrade' to create/update tables
    # DO NOT call db.create_all() here - it can cause data loss!

    # Initialize Kroger services and store in app config for blueprint access
    kroger_service = KrogerAPIService(
        app.config["CLIENT_ID"], app.config["CLIENT_SECRET"]
    )
    kroger_session_manager = KrogerSessionManager()
    kroger_workflow = KrogerWorkflow(kroger_service)

    # Store Kroger services in app config so blueprints can access them
    app.config["kroger_service"] = kroger_service
    app.config["kroger_session_manager"] = kroger_session_manager
    app.config["kroger_workflow"] = kroger_workflow

    # Register all blueprints
    register_blueprints(app)

    # Register Alexa API blueprint
    app.register_blueprint(alexa_bp)

    return app


# Create app instance
app = create_app()

# Add custom Jinja2 filter for EST datetime formatting
@app.template_filter("est_datetime")
def est_datetime_filter(dt, format="%I:%M %p"):
    """
    Format a datetime already stored in EST timezone.

    Returns an empty string for missing values to keep templates resilient.
    """
    if dt is None:
        return ""
    return dt.strftime(format)


# Special admin routes (no auth required for emergency access)
@app.route("/admin/setup-admin", methods=["GET", "POST"])
def setup_admin():
    """One-time setup to make a user an admin - NO AUTH REQUIRED for initial setup"""
    if request.method == "GET":
        return render_template("admin_setup.html")

    try:
        email = request.form.get("email")

        if not email:
            flash("❌ Email is required", "danger")
            return redirect(url_for("setup_admin"))

        logger.info(f"Looking for user with email: {email}")
        # Case-insensitive email lookup
        user = User.query.filter(db.func.lower(User.email) == email.lower()).first()

        if not user:
            flash(f"❌ No user found with email: {email}", "danger")
            return redirect(url_for("setup_admin"))

        # Make the user an admin
        user.is_admin = True
        db.session.commit()

        logger.info(f"User {user.username} ({user.email}) is now an admin!")
        flash(f"✅ User {user.username} ({user.email}) is now an admin!", "success")
        return redirect(url_for("main.homepage"))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin setup error: {e}", exc_info=True)
        flash(f"❌ Admin setup failed: {str(e)}", "danger")
        return redirect(url_for("setup_admin"))


@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""
    # Skip database queries for migration endpoints to avoid schema errors
    # Also skip for Alexa API endpoints (they use token-based auth, not session)
    if request.endpoint in ["migrate_database", "migrate_multi_household_endpoint"] or (
        request.endpoint and request.endpoint.startswith("alexa.")
    ):
        g.user = None
        return

    if CURR_USER_KEY in session:
        g.user = db.session.get(User, session[CURR_USER_KEY])

        # Update last activity timestamp
        if g.user and request.endpoint not in ["static", None]:
            g.user.last_activity = get_est_now()
            db.session.commit()
    else:
        g.user = None


@app.before_request
def add_household_to_g():
    """Add current household to Flask global."""
    # Skip for migration endpoint
    if request.endpoint == "migrate_database":
        g.household = None
        g.household_member = None
        return

    g.household = None
    g.household_member = None

    if g.user:
        # Get household from session or use the first one
        household_id = session.get("household_id")

        if household_id:
            # Verify user is a member of this household
            membership = HouseholdMember.query.filter_by(
                household_id=household_id, user_id=g.user.id
            ).first()

            if membership:
                g.household = db.session.get(Household, household_id)
                g.household_member = membership

        # If no household in session or invalid, get user's first household
        if not g.household:
            membership = HouseholdMember.query.filter_by(user_id=g.user.id).first()
            if membership:
                g.household = membership.household
                g.household_member = membership
                session["household_id"] = g.household.id


@app.before_request
def add_grocery_list_to_g():
    """Add current grocery list to Flask global."""
    # Skip for migration endpoint
    if request.endpoint == "migrate_database":
        g.grocery_list = None
        return

    g.grocery_list = None

    if g.user and g.household:
        # Try to get the grocery list from session first
        list_id = session.get(CURR_GROCERY_LIST_KEY)
        grocery_list = None

        if list_id:
            # Verify the list exists and belongs to the household
            grocery_list = GroceryList.query.filter_by(
                id=list_id, household_id=g.household.id
            ).first()

        # If no valid list in session, get the most recently modified planning list
        if not grocery_list:
            grocery_list = (
                GroceryList.query.filter_by(
                    household_id=g.household.id, status="planning"
                )
                .order_by(GroceryList.last_modified_at.desc())
                .first()
            )

        # If still no planning list, try to get ANY existing list from the household
        if not grocery_list:
            grocery_list = (
                GroceryList.query.filter_by(household_id=g.household.id)
                .order_by(GroceryList.last_modified_at.desc())
                .first()
            )

        # If still no list exists at all, create a default one
        if not grocery_list:
            grocery_list = GroceryList(
                household_id=g.household.id,
                user_id=g.user.id,
                created_by_user_id=g.user.id,
                name="Household Grocery List",
                status="planning",
            )
            db.session.add(grocery_list)
            db.session.commit()

        g.grocery_list = grocery_list
        session[CURR_GROCERY_LIST_KEY] = grocery_list.id


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
