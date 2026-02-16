"""Service for Kroger integration validation and common operations."""

from typing import Tuple, Optional
from flask import g, flash, redirect, url_for
from models import User
from constants import ErrorMessages, FlashCategory
from functools import wraps


class KrogerValidationService:
    """
    Service class for Kroger integration validation.
    
    Centralizes repeated validation logic following DRY principle.
    """

    @staticmethod
    def get_household_kroger_user() -> Optional[User]:
        """
        Get the Kroger-connected user for the current household.

        Returns:
            User object with Kroger credentials, or current user if no household Kroger user is set
        """
        if g.household and g.household.kroger_user_id:
            return User.query.get(g.household.kroger_user_id)
        return g.user

    @staticmethod
    def validate_kroger_connection(kroger_user: Optional[User]) -> Tuple[bool, Optional[str]]:
        """
        Validate that a user has a valid Kroger connection.

        Args:
            kroger_user: User object to check for Kroger credentials

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not kroger_user:
            return False, ErrorMessages.KROGER_USER_NOT_FOUND
        if not kroger_user.oauth_token:
            return False, ErrorMessages.KROGER_CONNECTION_REQUIRED
        return True, None

    @staticmethod
    def get_and_validate_kroger_user() -> Tuple[Optional[User], Optional[str]]:
        """
        Get household Kroger user and validate connection in one step.

        Returns:
            Tuple of (kroger_user, error_message). User is None if validation failed.
        """
        kroger_user = KrogerValidationService.get_household_kroger_user()
        is_valid, error_msg = KrogerValidationService.validate_kroger_connection(kroger_user)

        if not is_valid:
            return None, error_msg

        return kroger_user, None


def require_kroger_connection(f):
    """
    Decorator to ensure user has valid Kroger connection before accessing route.
    
    This decorator follows DRY principle by centralizing the repeated pattern of:
    1. Get household Kroger user
    2. Validate connection
    3. Flash error and redirect if invalid
    4. Proceed to route if valid
    
    Usage:
        @app.route('/some-kroger-route')
        @require_login
        @require_kroger_connection
        def some_kroger_route():
            # kroger_user is available in g.kroger_user
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        kroger_user, error_msg = KrogerValidationService.get_and_validate_kroger_user()

        if error_msg:
            flash(error_msg, FlashCategory.DANGER)
            return redirect(url_for("homepage"))

        # Make kroger_user available to the route
        g.kroger_user = kroger_user

        return f(*args, **kwargs)

    return decorated_function

