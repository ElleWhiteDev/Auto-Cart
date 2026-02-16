"""Base service class with common database operation patterns."""

from typing import Callable, Tuple, Optional, Any, TypeVar
from models import db
from logging_config import logger

T = TypeVar("T")


class BaseService:
    """
    Base service class providing common database operation patterns.
    
    This class implements the DRY principle by centralizing:
    - Transaction management (commit/rollback)
    - Error handling and logging
    - Consistent return patterns
    """

    @staticmethod
    def execute_with_transaction(
        operation: Callable[[], T],
        error_message: str = "Operation failed. Please try again.",
        operation_name: str = "database operation",
    ) -> Tuple[Optional[T], Optional[str]]:
        """
        Execute a database operation with automatic transaction management.

        This method follows the DRY principle by centralizing the common pattern of:
        1. Try to execute operation
        2. Commit on success
        3. Rollback on failure
        4. Log errors
        5. Return consistent tuple format

        Args:
            operation: Callable that performs the database operation
            error_message: User-friendly error message to return on failure
            operation_name: Name of operation for logging purposes

        Returns:
            Tuple of (result, error_message). Result is None if error occurred.

        Example:
            def create_user():
                user = User(name="John")
                db.session.add(user)
                return user
            
            user, error = BaseService.execute_with_transaction(
                create_user,
                "Failed to create user",
                "user creation"
            )
        """
        try:
            result = operation()
            db.session.commit()
            return result, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error during {operation_name}: {e}", exc_info=True)
            return None, error_message

    @staticmethod
    def execute_update_with_transaction(
        operation: Callable[[], None],
        error_message: str = "Update failed. Please try again.",
        operation_name: str = "database update",
    ) -> Tuple[bool, Optional[str]]:
        """
        Execute a database update operation with automatic transaction management.

        Similar to execute_with_transaction but returns bool instead of object.
        Useful for update/delete operations where you just need success/failure.

        Args:
            operation: Callable that performs the update operation
            error_message: User-friendly error message to return on failure
            operation_name: Name of operation for logging purposes

        Returns:
            Tuple of (success, error_message)

        Example:
            def update_user():
                user.name = "Jane"
            
            success, error = BaseService.execute_update_with_transaction(
                update_user,
                "Failed to update user",
                "user update"
            )
        """
        try:
            operation()
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error during {operation_name}: {e}", exc_info=True)
            return False, error_message

    @staticmethod
    def safe_strip(value: Optional[str]) -> Optional[str]:
        """
        Safely strip whitespace from a string value.

        Args:
            value: String to strip or None

        Returns:
            Stripped string or None if input was None or empty after stripping
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @staticmethod
    def validate_required_fields(**kwargs) -> Optional[str]:
        """
        Validate that required fields are present and not empty.

        Args:
            **kwargs: Field name and value pairs to validate

        Returns:
            Error message if validation fails, None if all fields are valid

        Example:
            error = BaseService.validate_required_fields(
                name=name,
                email=email
            )
            if error:
                return None, error
        """
        missing_fields = []
        for field_name, value in kwargs.items():
            if not value or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field_name)

        if missing_fields:
            fields_str = ", ".join(missing_fields)
            return f"Required fields missing: {fields_str}"

        return None

