
"""Utility functions for the Flask application."""

import base64
from functools import wraps
from urllib.parse import urlencode
from flask import session, flash, redirect, url_for, g
from typing import Optional, Dict, Any, List, Tuple

# Session keys
CURR_USER_KEY = "curr_user"
CURR_GROCERY_LIST_KEY = "curr_grocery_list"


def require_login(func):
    """Check user is logged in"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if CURR_USER_KEY not in session:
            flash('You must be logged in to view this page', 'danger')
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper


def do_login(user):
    """Log in user."""
    session[CURR_USER_KEY] = user.id


def do_logout():
    """Logout user."""
    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]
        if CURR_GROCERY_LIST_KEY in session:
            del session[CURR_GROCERY_LIST_KEY]


def initialize_session_defaults():
    """Initialize default session values if they don't exist."""
    defaults = {
        'show_modal': False,
        'products_for_cart': [],
        'items_to_choose_from': []
    }

    for key, default_value in defaults.items():
        if key not in session:
            session[key] = default_value


def clear_kroger_session_data():
    """Clear Kroger-related session data after cart operations."""
    session_keys_to_clear = [
        'products_for_cart',
        'items_to_choose_from',
        'location_id',
        'stores',
        'ingredient_names'
    ]

    for key in session_keys_to_clear:
        session.pop(key, None)

    session['show_modal'] = False


def encode_client_credentials(client_id: str, client_secret: str) -> str:
    """Encode client credentials for API authentication."""
    client_credentials = f"{client_id}:{client_secret}"
    return base64.b64encode(client_credentials.encode()).decode()


def build_oauth_url(base_url: str, client_id: str, redirect_uri: str, scope: str) -> str:
    """Build OAuth authorization URL."""
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': scope
    }
    return f"{base_url}/authorize?{urlencode(params)}"


def safe_get_json_value(response_json: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely extract value from JSON response."""
    return response_json.get(key, default)


def validate_required_fields(**kwargs) -> List[str]:
    """Validate that required fields are present and not empty."""
    missing_fields = []
    for field_name, value in kwargs.items():
        if not value or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field_name)
    return missing_fields
