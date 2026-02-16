"""
Recipe service layer for business logic related to recipes.
"""

from typing import List, Dict, Any, Optional, Tuple
from models import db, Recipe, RecipeIngredient, Household
from utils import parse_quantity_string
from logging_config import logger
from services.base_service import BaseService
from constants import ErrorMessages


class RecipeService(BaseService):
    """Service class for recipe-related business logic."""

    @staticmethod
    def create_recipe(
        household_id: int,
        name: str,
        ingredients_text: str,
        url: Optional[str] = None,
        notes: Optional[str] = None,
        created_by_user_id: Optional[int] = None,
    ) -> Tuple[Optional[Recipe], Optional[str]]:
        """
        Create a new recipe with ingredients.

        Args:
            household_id: ID of the household this recipe belongs to
            name: Recipe name
            ingredients_text: Raw ingredients text (one per line)
            url: Optional recipe URL
            notes: Optional recipe notes
            created_by_user_id: ID of user creating the recipe

        Returns:
            Tuple of (Recipe object, error message). Recipe is None if error occurred.
        """
        try:
            if not name or not name.strip():
                return None, "Recipe name is required."
            if created_by_user_id is None:
                return None, "A valid user is required to create a recipe."

            recipe = Recipe(
                user_id=created_by_user_id,
                household_id=household_id,
                name=name.strip(),
                url=url.strip() if url else None,
                notes=notes.strip() if notes else None,
            )
            db.session.add(recipe)
            db.session.flush()  # Get recipe ID without committing

            # Parse and add ingredients
            success, error = RecipeService._add_ingredients_to_recipe(
                recipe, ingredients_text
            )
            if not success:
                db.session.rollback()
                return None, error

            db.session.commit()
            return recipe, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating recipe: {e}", exc_info=True)
            return None, "Failed to create recipe. Please try again."

    @staticmethod
    def _add_ingredients_to_recipe(
        recipe: Recipe, ingredients_text: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Parse ingredients text and add to recipe.

        Args:
            recipe: Recipe object to add ingredients to
            ingredients_text: Raw ingredients text

        Returns:
            Tuple of (success, error_message)
        """
        try:
            ingredients = Recipe.parse_ingredients(ingredients_text)

            for ingredient_data in ingredients:
                quantity_value = parse_quantity_string(str(ingredient_data["quantity"]))
                if quantity_value is None:
                    quantity_value = 1.0

                ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_name=ingredient_data["ingredient_name"],
                    quantity=quantity_value,
                    measurement=ingredient_data["measurement"],
                )
                db.session.add(ingredient)

            return True, None

        except Exception as e:
            logger.error(f"Error parsing ingredients: {e}", exc_info=True)
            return False, "Failed to parse ingredients. Please check the format."

    @staticmethod
    def update_recipe(
        recipe: Recipe,
        name: Optional[str] = None,
        ingredients_text: Optional[str] = None,
        url: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Update an existing recipe.

        Args:
            recipe: Recipe object to update
            name: New recipe name (optional)
            ingredients_text: New ingredients text (optional)
            url: New URL (optional)
            notes: New notes (optional)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            if name is not None:
                recipe.name = name.strip()
            if url is not None:
                recipe.url = url.strip() if url else None
            if notes is not None:
                recipe.notes = notes.strip() if notes else None

            if ingredients_text is not None:
                # Remove old ingredients
                RecipeIngredient.query.filter_by(recipe_id=recipe.id).delete()

                # Add new ingredients
                success, error = RecipeService._add_ingredients_to_recipe(
                    recipe, ingredients_text
                )
                if not success:
                    db.session.rollback()
                    return False, error

            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating recipe: {e}", exc_info=True)
            return False, "Failed to update recipe. Please try again."

    @staticmethod
    def delete_recipe(recipe: Recipe) -> Tuple[bool, Optional[str]]:
        """
        Delete a recipe and all associated data.

        Args:
            recipe: Recipe object to delete

        Returns:
            Tuple of (success, error_message)
        """
        try:
            db.session.delete(recipe)
            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting recipe: {e}", exc_info=True)
            return False, "Failed to delete recipe. Please try again."
