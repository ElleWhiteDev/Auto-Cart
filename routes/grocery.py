"""
Grocery list management routes blueprint.

Handles grocery list CRUD operations and item management.
"""

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    g,
    session,
    jsonify,
)
from werkzeug.wrappers import Response

from extensions import db
from models import GroceryList, GroceryListItem
from utils import require_login, CURR_GROCERY_LIST_KEY
from logging_config import logger
from typing import Union

grocery_bp = Blueprint("grocery", __name__)


@grocery_bp.route("/update_grocery_list", methods=["POST"])
@require_login
def update_grocery_list() -> Response:
    """
    Add selected recipes to current grocery list.

    Returns:
        Redirect to homepage
    """
    selected_recipe_ids = request.form.getlist("recipe_ids")
    session["selected_recipe_ids"] = selected_recipe_ids

    grocery_list = g.grocery_list

    # If no grocery list exists, create a default one
    if not grocery_list and g.household:
        grocery_list = GroceryList(
            household_id=g.household.id,
            user_id=g.user.id,
            created_by_user_id=g.user.id,
            name="Household Grocery List",
            status="planning",
        )
        db.session.add(grocery_list)
        db.session.commit()
        session[CURR_GROCERY_LIST_KEY] = grocery_list.id
        g.grocery_list = grocery_list

    GroceryList.update_grocery_list(
        selected_recipe_ids, grocery_list=grocery_list, user_id=g.user.id
    )
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/grocery-list/create", methods=["POST"])
@require_login
def create_grocery_list() -> Response:
    """
    Create a new grocery list for the household.

    Returns:
        Redirect to homepage
    """
    if not g.household:
        flash("You must be in a household to create a grocery list", "danger")
        return redirect(url_for("main.homepage"))

    list_name = request.form.get("list_name", "").strip()
    if not list_name:
        flash("Please enter a list name", "danger")
        return redirect(url_for("main.homepage"))

    new_list = GroceryList(
        household_id=g.household.id,
        user_id=g.user.id,
        created_by_user_id=g.user.id,
        name=list_name,
        status="planning",
    )
    db.session.add(new_list)
    db.session.commit()

    # Switch to the new list
    session[CURR_GROCERY_LIST_KEY] = new_list.id

    flash(f'Grocery list "{list_name}" created successfully!', "success")
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/grocery-list/switch/<int:list_id>", methods=["POST"])
@require_login
def switch_grocery_list(list_id: int) -> Response:
    """
    Switch to a different grocery list.

    Args:
        list_id: Grocery list ID

    Returns:
        Redirect to homepage
    """
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id, household_id=g.household.id
    ).first()

    if not grocery_list:
        flash("Grocery list not found", "danger")
        return redirect(url_for("main.homepage"))

    session[CURR_GROCERY_LIST_KEY] = list_id
    flash(f'Switched to "{grocery_list.name}"', "success")
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/grocery-list/rename/<int:list_id>", methods=["POST"])
@require_login
def rename_grocery_list(list_id: int) -> Response:
    """
    Rename a grocery list.

    Args:
        list_id: Grocery list ID

    Returns:
        Redirect to homepage
    """
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id, household_id=g.household.id
    ).first()

    if not grocery_list:
        flash("Grocery list not found", "danger")
        return redirect(url_for("main.homepage"))

    new_name = request.form.get("list_name", "").strip()
    if not new_name:
        flash("Please enter a list name", "danger")
        return redirect(url_for("main.homepage"))

    old_name = grocery_list.name
    grocery_list.name = new_name
    db.session.commit()

    flash(f'Renamed "{old_name}" to "{new_name}"', "success")
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/grocery-list/delete/<int:list_id>", methods=["POST"])
@require_login
def delete_grocery_list(list_id: int) -> Response:
    """
    Delete a grocery list.

    Args:
        list_id: Grocery list ID

    Returns:
        Redirect to homepage
    """
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id, household_id=g.household.id
    ).first()

    if not grocery_list:
        flash("Grocery list not found", "danger")
        return redirect(url_for("main.homepage"))

    # Don't allow deleting the last list
    all_lists = GroceryList.query.filter_by(household_id=g.household.id).all()
    if len(all_lists) <= 1:
        flash("Cannot delete the last grocery list", "danger")
        return redirect(url_for("main.homepage"))

    # If deleting current list, switch to another one
    if session.get(CURR_GROCERY_LIST_KEY) == list_id:
        other_list = next((l for l in all_lists if l.id != list_id), None)
        if other_list:
            session[CURR_GROCERY_LIST_KEY] = other_list.id

    list_name = grocery_list.name
    db.session.delete(grocery_list)
    db.session.commit()

    flash(f'Deleted "{list_name}"', "success")
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/clear_grocery_list", methods=["POST"])
@require_login
def clear_grocery_list() -> Response:
    """
    Clear all items from the current grocery list.

    Returns:
        Redirect to homepage
    """
    grocery_list = g.grocery_list

    if grocery_list:
        # Delete all grocery list items
        for item in grocery_list.items:
            db.session.delete(item)
        db.session.commit()
        flash("Grocery list cleared successfully!", "success")
    else:
        flash("No grocery list found", "error")

    # Clear selected recipe IDs from session
    session.pop("selected_recipe_ids", None)

    return redirect(url_for("main.homepage"))


@grocery_bp.route("/shopping-mode")
@require_login
def shopping_mode() -> Union[str, Response]:
    """
    Streamlined shopping interface.

    Returns:
        Rendered shopping mode template or redirect to homepage
    """
    if not g.grocery_list:
        flash("Please select a grocery list first", "warning")
        return redirect(url_for("main.homepage"))

    grocery_list = g.grocery_list

    # Get all items with their ingredients
    items = GroceryListItem.query.filter_by(grocery_list_id=grocery_list.id).all()

    # Calculate progress
    total_items = len(items)
    checked_items = sum(1 for item in items if item.is_checked)

    return render_template(
        "shopping_mode.html",
        grocery_list=grocery_list,
        items=items,
        total_items=total_items,
        checked_items=checked_items,
    )


@grocery_bp.route("/shopping-mode/start", methods=["POST"])
@require_login
def start_shopping() -> Response:
    """
    Start a shopping session.

    Returns:
        Redirect to shopping mode
    """
    if not g.grocery_list:
        flash("Please select a grocery list first", "warning")
        return redirect(url_for("main.homepage"))

    grocery_list = g.grocery_list
    grocery_list.status = "shopping"
    grocery_list.shopping_user_id = g.user.id
    grocery_list.last_modified_by_user_id = g.user.id

    db.session.commit()

    flash("Shopping session started!", "success")
    return redirect(url_for("grocery.shopping_mode"))


@grocery_bp.route("/shopping-mode/end", methods=["POST"])
@require_login
def end_shopping() -> Response:
    """
    End a shopping session and remove checked items.

    Returns:
        Redirect to homepage
    """
    if not g.grocery_list:
        flash("Please select a grocery list first", "warning")
        return redirect(url_for("main.homepage"))

    grocery_list = g.grocery_list

    # Delete all checked items
    checked_items = GroceryListItem.query.filter_by(
        grocery_list_id=grocery_list.id, completed=True
    ).all()

    num_removed = len(checked_items)
    for item in checked_items:
        db.session.delete(item)

    grocery_list.status = "planning"
    grocery_list.shopping_user_id = None
    grocery_list.last_modified_by_user_id = g.user.id

    db.session.commit()

    flash(f"Shopping complete! Removed {num_removed} items.", "success")
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/shopping-mode/toggle/<int:item_id>", methods=["POST"])
@require_login
def toggle_item(item_id: int) -> tuple[dict, int]:
    """
    Toggle item checked status.

    Args:
        item_id: Grocery list item ID

    Returns:
        JSON response with updated status
    """
    item = GroceryListItem.query.get_or_404(item_id)

    if item.grocery_list_id != g.grocery_list.id:
        return jsonify({"error": "Unauthorized"}), 403

    item.is_checked = not item.is_checked

    # Update last modified
    grocery_list = g.grocery_list
    grocery_list.last_modified_by_user_id = g.user.id

    db.session.commit()

    return jsonify({"success": True, "is_checked": item.is_checked, "item_id": item.id})
