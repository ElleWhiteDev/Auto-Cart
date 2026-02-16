"""
Grocery list service layer for business logic related to grocery lists.
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from models import db, GroceryList, GroceryListItem, Recipe, RecipeIngredient
from utils import parse_quantity_string
from logging_config import logger
from services.base_service import BaseService
from constants import ErrorMessages


class GroceryListService(BaseService):
    """Service class for grocery list-related business logic."""

    @staticmethod
    def create_grocery_list(
        household_id: int,
        name: str,
        created_by_user_id: int,
    ) -> Tuple[Optional[GroceryList], Optional[str]]:
        """
        Create a new grocery list.

        Args:
            household_id: ID of the household
            name: Name of the grocery list
            created_by_user_id: ID of user creating the list

        Returns:
            Tuple of (GroceryList object, error message)
        """

        def create_operation():
            grocery_list = GroceryList(
                household_id=household_id,
                name=BaseService.safe_strip(name),
                created_by_user_id=created_by_user_id,
                last_modified_by_user_id=created_by_user_id,
            )
            db.session.add(grocery_list)
            return grocery_list

        return BaseService.execute_with_transaction(
            create_operation,
            ErrorMessages.GROCERY_LIST_CREATE_ERROR,
            "grocery list creation",
        )

    @staticmethod
    def add_recipes_to_list(
        grocery_list: GroceryList,
        recipe_ids: List[int],
        user_id: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Add recipes to a grocery list with ingredient consolidation.

        Args:
            grocery_list: GroceryList object
            recipe_ids: List of recipe IDs to add
            user_id: ID of user performing the action

        Returns:
            Tuple of (success, error_message)
        """

        def add_operation():
            # Get all ingredients from selected recipes
            ingredients = RecipeIngredient.query.filter(
                RecipeIngredient.recipe_id.in_(recipe_ids)
            ).all()

            # Consolidate ingredients by name and measurement
            consolidated = GroceryListService._consolidate_ingredients(ingredients)

            # Add consolidated ingredients to grocery list
            for key, data in consolidated.items():
                item = GroceryListItem(
                    grocery_list_id=grocery_list.id,
                    ingredient_name=data["name"],
                    quantity=data["quantity"],
                    measurement=data["measurement"],
                    is_checked=False,
                )
                db.session.add(item)

            grocery_list.last_modified_by_user_id = user_id

        return BaseService.execute_update_with_transaction(
            add_operation,
            "Failed to add recipes to list. Please try again.",
            "adding recipes to grocery list",
        )

    @staticmethod
    def _consolidate_ingredients(
        ingredients: List[RecipeIngredient],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Consolidate ingredients by combining quantities of same ingredient/measurement.

        Args:
            ingredients: List of RecipeIngredient objects

        Returns:
            Dictionary mapping (name, measurement) to consolidated data
        """
        consolidated = defaultdict(lambda: {"quantity": 0.0, "name": "", "measurement": ""})

        for ingredient in ingredients:
            key = (
                ingredient.ingredient_name.lower().strip(),
                ingredient.measurement.lower().strip(),
            )

            quantity = parse_quantity_string(ingredient.quantity)
            if quantity is not None:
                consolidated[key]["quantity"] += quantity

            # Store original casing for display
            if not consolidated[key]["name"]:
                consolidated[key]["name"] = ingredient.ingredient_name
                consolidated[key]["measurement"] = ingredient.measurement

        return consolidated

    @staticmethod
    def toggle_item_checked(
        item: GroceryListItem,
        user_id: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Toggle the checked status of a grocery list item.

        Args:
            item: GroceryListItem object
            user_id: ID of user performing the action

        Returns:
            Tuple of (success, error_message)
        """

        def toggle_operation():
            item.is_checked = not item.is_checked
            item.grocery_list.last_modified_by_user_id = user_id

        return BaseService.execute_update_with_transaction(
            toggle_operation,
            "Failed to update item. Please try again.",
            "toggling grocery list item",
        )

    @staticmethod
    def clear_grocery_list(
        grocery_list: GroceryList,
        user_id: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Clear all items from a grocery list.

        Args:
            grocery_list: GroceryList object
            user_id: ID of user performing the action

        Returns:
            Tuple of (success, error_message)
        """

        def clear_operation():
            GroceryListItem.query.filter_by(grocery_list_id=grocery_list.id).delete()
            grocery_list.last_modified_by_user_id = user_id

        return BaseService.execute_update_with_transaction(
            clear_operation,
            "Failed to clear grocery list. Please try again.",
            "clearing grocery list",
        )
