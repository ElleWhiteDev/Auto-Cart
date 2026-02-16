"""Utility functions for the Flask application."""

import base64
from functools import wraps
from urllib.parse import urlencode
from flask import session, flash, redirect, url_for, g
from typing import Optional, Dict, Any, List, Tuple
from fractions import Fraction
from datetime import datetime
import pytz
from constants import SessionKeys, ErrorMessages, FlashCategory, DEFAULT_TIMEZONE

# Session keys - kept for backward compatibility, use SessionKeys enum in new code
CURR_USER_KEY = SessionKeys.CURR_USER
CURR_GROCERY_LIST_KEY = SessionKeys.CURR_GROCERY_LIST


# Timezone utilities
def get_est_now():
    """Get current time in EST timezone as a timezone-naive datetime"""
    est = pytz.timezone(DEFAULT_TIMEZONE)
    # Get current time in EST and remove timezone info for database storage
    return datetime.now(est).replace(tzinfo=None)


def get_est_date():
    """Get current date in EST timezone"""
    return get_est_now().date()


def require_login(func):
    """Check user is logged in"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if CURR_USER_KEY not in session:
            flash(ErrorMessages.LOGIN_REQUIRED, FlashCategory.DANGER)
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


def require_admin(func):
    """Check user is logged in and is an admin"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if CURR_USER_KEY not in session:
            flash(ErrorMessages.LOGIN_REQUIRED, FlashCategory.DANGER)
            return redirect(url_for("login"))
        if not g.user or not g.user.is_admin:
            flash(ErrorMessages.ADMIN_REQUIRED, FlashCategory.DANGER)
            return redirect(url_for("homepage"))
        return func(*args, **kwargs)

    return wrapper


def do_login(user):
    """Log in user."""
    session[CURR_USER_KEY] = user.id
    session.permanent = True  # Make session persistent


def do_logout():
    """Logout user."""
    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]
        if CURR_GROCERY_LIST_KEY in session:
            del session[CURR_GROCERY_LIST_KEY]


def initialize_session_defaults():
    """Initialize default session values if they don't exist."""
    defaults = {
        SessionKeys.SHOW_MODAL: False,
        SessionKeys.PRODUCTS_FOR_CART: [],
        SessionKeys.ITEMS_TO_CHOOSE_FROM: [],
    }

    for key, default_value in defaults.items():
        if key not in session:
            session[key] = default_value


def encode_client_credentials(client_id: str, client_secret: str) -> str:
    """Encode client credentials for API authentication."""
    client_credentials = f"{client_id}:{client_secret}"
    return base64.b64encode(client_credentials.encode()).decode()


def build_oauth_url(
    base_url: str, client_id: str, redirect_uri: str, scope: str
) -> str:
    """Build OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
    }
    return f"{base_url}/authorize?{urlencode(params)}"


def safe_get_json_value(
    response_json: Dict[str, Any], key: str, default: Any = None
) -> Any:
    """Safely extract value from JSON response."""
    return response_json.get(key, default)


def validate_required_fields(**kwargs) -> List[str]:
    """Validate that required fields are present and not empty."""
    missing_fields = []
    for field_name, value in kwargs.items():
        if not value or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field_name)
    return missing_fields


def parse_quantity_string(quantity_string: str) -> Optional[float]:
    """
    Parse a quantity string into a float value.
    Handles fractions (e.g., "1/2", "3/4") and decimal numbers.

    Args:
        quantity_string: String representation of a quantity

    Returns:
        Float value or None if parsing fails
    """
    if not quantity_string or quantity_string.strip() == "":
        return 0.0

    quantity_string = str(quantity_string).strip()

    try:
        # Handle fractions
        if "/" in quantity_string:
            return float(Fraction(quantity_string))
        # Handle regular floats/ints
        return float(quantity_string)
    except (ValueError, ZeroDivisionError):
        return None


def is_valid_float(value: str) -> bool:
    """Check if a value can be converted to float."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def get_household_kroger_user(household, current_user):
    """
    Get the Kroger-connected user for a household.

    Args:
        household: Household object or None
        current_user: Current logged-in user

    Returns:
        User object with Kroger credentials, or current_user if no household Kroger user is set
    """
    if household and household.kroger_user_id:
        from models import User
        return User.query.get(household.kroger_user_id)
    return current_user


def validate_kroger_connection(kroger_user) -> Tuple[bool, Optional[str]]:
    """
    Validate that a user has a valid Kroger connection.

    Args:
        kroger_user: User object to check for Kroger credentials

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not kroger_user:
        return False, "User not found"
    if not kroger_user.oauth_token:
        return False, "Please connect a Kroger account first"
    return True, None
