"""
Standardized API response handling for AJAX endpoints.
"""

from typing import Any, Dict, Optional
from flask import jsonify
from http import HTTPStatus


class APIResponse:
    """Standardized API response builder for consistent AJAX responses."""

    @staticmethod
    def success(
        data: Optional[Any] = None,
        message: Optional[str] = None,
        status_code: int = HTTPStatus.OK,
    ):
        """
        Create a successful API response.

        Args:
            data: Response data (optional)
            message: Success message (optional)
            status_code: HTTP status code (default: 200)

        Returns:
            Flask JSON response with standardized format
        """
        response = {"success": True}
        
        if data is not None:
            response["data"] = data
        
        if message:
            response["message"] = message
        
        return jsonify(response), status_code

    @staticmethod
    def error(
        error: str,
        status_code: int = HTTPStatus.BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Create an error API response.

        Args:
            error: Error message
            status_code: HTTP status code (default: 400)
            details: Additional error details (optional)

        Returns:
            Flask JSON response with standardized error format
        """
        response = {
            "success": False,
            "error": error,
        }
        
        if details:
            response["details"] = details
        
        return jsonify(response), status_code

    @staticmethod
    def validation_error(
        errors: Dict[str, str],
        message: str = "Validation failed",
    ):
        """
        Create a validation error response.

        Args:
            errors: Dictionary of field names to error messages
            message: General validation error message

        Returns:
            Flask JSON response with validation errors
        """
        return APIResponse.error(
            error=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            details={"validation_errors": errors},
        )

    @staticmethod
    def not_found(
        resource: str = "Resource",
        message: Optional[str] = None,
    ):
        """
        Create a not found error response.

        Args:
            resource: Name of the resource that wasn't found
            message: Custom error message (optional)

        Returns:
            Flask JSON response for 404 error
        """
        error_message = message or f"{resource} not found"
        return APIResponse.error(
            error=error_message,
            status_code=HTTPStatus.NOT_FOUND,
        )

    @staticmethod
    def unauthorized(
        message: str = "Unauthorized access",
    ):
        """
        Create an unauthorized error response.

        Args:
            message: Error message

        Returns:
            Flask JSON response for 401 error
        """
        return APIResponse.error(
            error=message,
            status_code=HTTPStatus.UNAUTHORIZED,
        )

    @staticmethod
    def forbidden(
        message: str = "Access forbidden",
    ):
        """
        Create a forbidden error response.

        Args:
            message: Error message

        Returns:
            Flask JSON response for 403 error
        """
        return APIResponse.error(
            error=message,
            status_code=HTTPStatus.FORBIDDEN,
        )

    @staticmethod
    def server_error(
        message: str = "An internal server error occurred",
        log_error: bool = True,
    ):
        """
        Create a server error response.

        Args:
            message: Error message
            log_error: Whether to log the error (default: True)

        Returns:
            Flask JSON response for 500 error
        """
        if log_error:
            from logging_config import logger
            logger.error(f"Server error: {message}")
        
        return APIResponse.error(
            error=message,
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

