"""Utility functions for the Flask application."""

import base64
from functools import wraps
from urllib.parse import urlencode
from flask import session, flash, redirect, url_for, g, Response
from typing import Optional, Dict, Any, List, Tuple, Callable, Union
from fractions import Fraction
from datetime import datetime, date
import pytz
from constants import SessionKeys, ErrorMessages, FlashCategory, DEFAULT_TIMEZONE

# Session keys - kept for backward compatibility, use SessionKeys enum in new code
CURR_USER_KEY = SessionKeys.CURR_USER
CURR_GROCERY_LIST_KEY = SessionKeys.CURR_GROCERY_LIST


# Timezone utilities
def get_est_now() -> datetime:
    """Get current time in EST timezone as a timezone-naive datetime"""
    est = pytz.timezone(DEFAULT_TIMEZONE)
    # Get current time in EST and remove timezone info for database storage
    return datetime.now(est).replace(tzinfo=None)


def get_est_date() -> date:
    """Get current date in EST timezone"""
    return get_est_now().date()


def require_login(func: Callable) -> Callable:
    """Check user is logged in"""

    @wraps(func)
    def wrapper(*args, **kwargs) -> Union[str, Response]:
        if CURR_USER_KEY not in session:
            flash(ErrorMessages.LOGIN_REQUIRED, FlashCategory.DANGER)
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


def require_admin(func: Callable) -> Callable:
    """Check user is logged in and is an admin"""

    @wraps(func)
    def wrapper(*args, **kwargs) -> Union[str, Response]:
        if CURR_USER_KEY not in session:
            flash(ErrorMessages.LOGIN_REQUIRED, FlashCategory.DANGER)
            return redirect(url_for("auth.login"))
        if not g.user or not g.user.is_admin:
            flash(ErrorMessages.ADMIN_REQUIRED, FlashCategory.DANGER)
            return redirect(url_for("main.homepage"))
        return func(*args, **kwargs)

    return wrapper


def do_login(user: Any) -> None:
    """Log in user."""
    session[CURR_USER_KEY] = user.id
    session.permanent = True  # Make session persistent


def do_logout() -> None:
    """Logout user."""
    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]
        if CURR_GROCERY_LIST_KEY in session:
            del session[CURR_GROCERY_LIST_KEY]


def initialize_session_defaults() -> None:
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


def parse_simple_ingredient(ingredient_text: str) -> List[Dict[str, str]]:
    """
    Basic ingredient parser used for manual ingredient entry fallbacks.

    Returns:
        List of parsed ingredient dicts with quantity, measurement, and ingredient_name.
    """
    import re

    ingredient_text = ingredient_text.strip()
    if not ingredient_text:
        return []

    pattern = r"^(\d+(?:/\d+)?(?:\.\d+)?)\s+(\w+)\s+(.*)"
    match = re.match(pattern, ingredient_text)
    if match:
        quantity, measurement, ingredient_name = match.groups()
        return [
            {
                "quantity": quantity.strip(),
                "measurement": measurement.strip(),
                "ingredient_name": ingredient_name.strip(),
            }
        ]

    # Default fallback (treat the text as a single unit)
    return [
        {
            "quantity": "1",
            "measurement": "unit",
            "ingredient_name": ingredient_text,
        }
    ]


def is_valid_float(value: str) -> bool:
    """Check if a value can be converted to float."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def get_household_kroger_user(household: Optional[Any], current_user: Any) -> Any:
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


def send_generic_invitation_email(
    recipient_email: str,
    recipient_name: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> None:
    """
    Send a generic invitation email about Auto-Cart.

    Args:
        recipient_email: Email address of the recipient
        recipient_name: Optional name of the recipient for personalization
        sender_name: Optional name of the sender for personalization
    """
    from flask import request, current_app
    from flask_mail import Message
    from extensions import mail
    from logging_config import logger

    # Build registration URL
    base_url = request.url_root.rstrip("/")
    register_url = f"{base_url}/register"

    # Get response email from config
    response_email = current_app.config.get(
        "MAIL_DEFAULT_SENDER", "support@autocart.com"
    )

    # Personalize greeting if name provided
    greeting = f"Hi {recipient_name}" if recipient_name else "Hi there"

    # Personalize opening line if sender name provided
    if sender_name:
        opening_line = f"{sender_name} wanted to share Auto-Cart with you - it's a free web app for organizing recipes, planning meals, and managing grocery shopping. It's been a game-changer for keeping the kitchen organized!"
    else:
        opening_line = "I wanted to share Auto-Cart with you - it's a free web app I've been using to organize recipes, plan meals, and manage grocery shopping. It's been a game-changer for keeping my kitchen organized!"

    subject = "Check out Auto-Cart - Your Kitchen's New Best Friend!"

    # Create HTML email body (truncated for brevity - full version in original)
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #004c91 0%, #1e6bb8 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 5px 5px 0 0; }}
            .content {{ background-color: #f9f9f9; padding: 30px; border: 1px solid #ddd; }}
            .button {{ display: inline-block; padding: 12px 24px; background-color: #004c91; color: white !important; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: 600; }}
            .features {{ background-color: white; padding: 20px; margin: 20px 0; border-left: 4px solid #004c91; border-radius: 5px; }}
            .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to Auto-Cart!</h1>
            </div>
            <div class="content">
                <p><strong>{greeting}!</strong></p>
                <p>{opening_line}</p>

                <div class="features">
                    <h3>🛒 What Makes Auto-Cart Special?</h3>
                    <ul>
                        <li><strong>Recipe & Meal Planning</strong> - Save recipes, plan meals, assign cooks</li>
                        <li><strong>Smart Shopping</strong> - Auto-generate lists, Kroger integration</li>
                        <li><strong>Multiple Households</strong> - Manage multiple households easily</li>
                        <li><strong>AI-Powered</strong> - Smart consolidation and recipe parsing</li>
                    </ul>
                </div>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{register_url}" class="button">Try Auto-Cart Free</a>
                </div>

                <p style="text-align: center; color: #666; font-size: 14px;">
                    It's completely free to use - no credit card required!
                </p>
            </div>
            <div class="footer">
                <p>This invitation was sent from Auto-Cart</p>
                <p>Questions? Reply to <a href="mailto:{response_email}">{response_email}</a></p>
            </div>
        </div>
    </body>
    </html>
    """

    # Create plain text version
    text_body = f"""
{greeting}!

{opening_line}

WHAT MAKES AUTO-CART SPECIAL?
• Recipe & Meal Planning - Save recipes, plan meals, assign cooks
• Smart Shopping - Auto-generate lists, Kroger integration
• Multiple Households - Manage multiple households easily
• AI-Powered - Smart consolidation and recipe parsing

GET STARTED:
Try Auto-Cart free at: {register_url}
(No credit card required!)

---
This invitation was sent from Auto-Cart
Questions? Reply to {response_email}
    """

    msg = Message(
        subject=subject, recipients=[recipient_email], html=html_body, body=text_body
    )

    mail.send(msg)
    logger.info(f"Generic invitation email sent to {recipient_email}")
