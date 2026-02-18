"""
API routes blueprint.

Handles AJAX/API endpoints for dynamic content updates.
"""

from flask import Blueprint, jsonify, g
from werkzeug.wrappers import Response

from models import GroceryList, GroceryListItem
from utils import require_login
from typing import Union

api_bp = Blueprint("api", __name__)


@api_bp.route("/grocery-list/<int:list_id>/state")
@require_login
def grocery_list_state(list_id: int) -> Union[tuple[dict, int], Response]:
    """
    Get current state of grocery list for polling.

    Args:
        list_id: Grocery list ID

    Returns:
        JSON response with list state
    """
    grocery_list = GroceryList.query.get_or_404(list_id)

    # Check authorization
    if grocery_list.household_id != g.household.id:
        return jsonify({"error": "Unauthorized"}), 403

    # Get item count
    item_count = GroceryListItem.query.filter_by(grocery_list_id=list_id).count()
    checked_count = GroceryListItem.query.filter_by(
        grocery_list_id=list_id, is_checked=True
    ).count()

    return jsonify(
        {
            "status": grocery_list.status,
            "last_modified_at": grocery_list.last_modified_at.isoformat()
            if grocery_list.last_modified_at
            else None,
            "last_modified_by": grocery_list.last_modified_by.username
            if grocery_list.last_modified_by
            else None,
            "shopping_user": grocery_list.shopping_user.username
            if grocery_list.shopping_user
            else None,
            "item_count": item_count,
            "checked_count": checked_count,
        }
    )
