"""
Routes package for Auto-Cart application.

This package contains all route blueprints organized by functionality:
- auth: Authentication and user management
- recipes: Recipe CRUD operations
- grocery: Grocery list management
- meal_plan: Meal planning features
- kroger: Kroger API integration
- admin: Administrative functions
- api: AJAX/API endpoints
"""

from flask import Flask
from .main import main_bp
from .auth import auth_bp
from .recipes import recipes_bp
from .grocery import grocery_bp
from .meal_plan import meal_plan_bp
from .kroger import kroger_bp
from .admin import admin_bp
from .api import api_bp


def register_blueprints(app: Flask) -> None:
    """
    Register all blueprints with the Flask application.

    Args:
        app: Flask application instance
    """
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(grocery_bp)
    app.register_blueprint(meal_plan_bp)
    app.register_blueprint(kroger_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")
