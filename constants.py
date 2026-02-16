"""Application-wide constants to avoid magic strings and promote DRY principle."""

from enum import Enum


class FlashCategory(str, Enum):
    """Flash message categories for consistent UI feedback."""

    SUCCESS = "success"
    DANGER = "danger"
    WARNING = "warning"
    INFO = "info"
    ERROR = "error"


class MealType(str, Enum):
    """Valid meal types for meal planning."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"

    @classmethod
    def values(cls):
        """Get list of all valid meal type values."""
        return [meal_type.value for meal_type in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid meal type."""
        return value.lower() in cls.values()


class RecipeVisibility(str, Enum):
    """Recipe visibility options."""

    PRIVATE = "private"
    HOUSEHOLD = "household"


class HouseholdRole(str, Enum):
    """Household member roles."""

    OWNER = "owner"
    MEMBER = "member"


class SessionKeys:
    """Session key constants to avoid typos and promote consistency."""

    CURR_USER = "curr_user"
    CURR_GROCERY_LIST = "curr_grocery_list"
    SHOW_MODAL = "show_modal"
    PRODUCTS_FOR_CART = "products_for_cart"
    ITEMS_TO_CHOOSE_FROM = "items_to_choose_from"
    SELECTED_RECIPE_IDS = "selected_recipe_ids"
    LOCATION_ID = "location_id"
    CURRENT_INGREDIENT_DETAIL = "current_ingredient_detail"


class ErrorMessages:
    """Standard error messages for consistency."""

    # Authentication errors
    LOGIN_REQUIRED = "You must be logged in to view this page"
    ADMIN_REQUIRED = "Access denied. Admin privileges required."
    INVALID_CREDENTIALS = "Invalid username or password"

    # Kroger integration errors
    KROGER_AUTH_ERROR = "Authentication error. Please try again."
    KROGER_CONNECTION_REQUIRED = "Please connect a Kroger account first"
    KROGER_USER_NOT_FOUND = "User not found"

    # Form validation errors
    FORM_VALIDATION_FAILED = "Form validation failed. Please check your input."
    REQUIRED_FIELD_MISSING = "Required field is missing"

    # Database errors
    DB_COMMIT_ERROR = "An error occurred. Please try again."
    RECIPE_CREATE_ERROR = "Error Occurred. Please try again"
    RECIPE_UPDATE_ERROR = "Failed to update recipe. Please try again."
    GROCERY_LIST_CREATE_ERROR = "Failed to create grocery list. Please try again."

    # User registration errors
    EMAIL_TAKEN = "Email already taken"
    USERNAME_TAKEN = "Username already taken"

    # Ingredient parsing errors
    INGREDIENT_PARSE_ERROR = (
        'Could not parse ingredient. Please use format like "2 cups flour" or just "pickles"'
    )


class SuccessMessages:
    """Standard success messages for consistency."""

    RECIPE_CREATED = "Recipe created successfully!"
    RECIPE_UPDATED = "Recipe updated successfully!"
    KROGER_CONNECTED = "Successfully connected to Kroger!"
    WELCOME_NEW_USER = "Welcome! Please create or join a household to get started."
    PASSWORD_UPDATED = "Password updated successfully!"
    EMAIL_UPDATED = "Email updated successfully!"
    USERNAME_UPDATED = "Username updated successfully!"


# API Configuration
KROGER_API_SCOPE = "cart.basic:write product.compact profile.compact"
KROGER_API_BASE_URL = "https://api.kroger.com/v1"
KROGER_OAUTH_BASE_URL = "https://api.kroger.com/v1/connect/oauth2"

# Pagination defaults
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# Validation constraints
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 20
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 20

# Timezone
DEFAULT_TIMEZONE = "US/Eastern"

