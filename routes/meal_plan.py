"""
Meal planning routes blueprint.

Handles meal plan CRUD operations and email notifications.
"""

from datetime import datetime, timedelta
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

from extensions import db, mail
from models import (
    MealPlanEntry,
    GroceryList,
    Recipe,
    User,
    MealPlanChange,
    HouseholdMember,
)
from utils import require_login, CURR_GROCERY_LIST_KEY, get_est_date
from logging_config import logger
from typing import Union, Dict, Any

meal_plan_bp = Blueprint("meal_plan", __name__)


@meal_plan_bp.route("/meal-plan")
@require_login
def meal_plan() -> Union[str, Response]:
    """
    Show weekly meal plan for household.

    Returns:
        Rendered meal plan template or redirect to homepage
    """
    if not g.household:
        flash("Please create or join a household first", "warning")
        return redirect(url_for("main.homepage"))

    # Get week offset from query params (0 = this week, 1 = next week, etc.)
    week_offset = int(request.args.get("week", 0))

    # Calculate start of week (Monday)
    today = datetime.now().date()
    days_since_monday = today.weekday()
    week_start = (
        today - timedelta(days=days_since_monday) + timedelta(weeks=week_offset)
    )
    week_end = week_start + timedelta(days=6)

    # Get meal plan entries for this week
    meal_entries = MealPlanEntry.query.filter(
        MealPlanEntry.household_id == g.household.id,
        MealPlanEntry.date >= week_start,
        MealPlanEntry.date <= week_end,
    ).all()

    # Get all household recipes for the dropdown
    recipes = Recipe.query.filter(
        (Recipe.household_id == g.household.id)
        | ((Recipe.user_id == g.user.id) & (Recipe.household_id.is_(None)))
    ).all()

    # Get household members for cook assignment
    from models import HouseholdMember

    household_members = HouseholdMember.query.filter_by(
        household_id=g.household.id
    ).all()
    household_users = [m.user for m in household_members]

    # Organize entries by day and meal type
    meal_plan_grid = {}
    for i in range(7):
        day = week_start + timedelta(days=i)
        meal_plan_grid[day] = {"breakfast": [], "lunch": [], "dinner": [], "snack": []}

    for entry in meal_entries:
        if entry.date in meal_plan_grid:
            meal_plan_grid[entry.date][entry.meal_type].append(entry)

    return render_template(
        "meal_plan.html",
        meal_plan_grid=meal_plan_grid,
        meal_plan=meal_plan_grid,
        week_start=week_start,
        week_end=week_end,
        week_offset=week_offset,
        recipes=recipes,
        household_users=household_users,
        today=today,
    )


@meal_plan_bp.route("/meal-plan/add", methods=["POST"])
@require_login
def add_meal_plan_entry() -> Response:
    """
    Add a recipe to the meal plan.

    Returns:
        Redirect to meal plan page
    """
    if not g.household:
        flash("Please create or join a household first", "warning")
        return redirect(url_for("main.homepage"))

    recipe_id = request.form.get("recipe_id")
    custom_meal_name = request.form.get("custom_meal_name", "").strip()
    date_str = request.form.get("date")
    meal_type = request.form.get("meal_type")
    assigned_cook_ids = [
        int(cook_id)
        for cook_id in request.form.getlist("assigned_cook_ids")
        if cook_id and cook_id.strip()
    ]
    notes = request.form.get("notes", "").strip()

    # Validate required fields
    if not date_str or not meal_type:
        flash("Date and meal type are required", "danger")
        return redirect(
            url_for("meal_plan.meal_plan")
            + f"?week={request.form.get('week_offset', 0)}"
        )

    # Must have either recipe_id or custom_meal_name
    if not recipe_id and not custom_meal_name:
        flash("Please select a recipe or enter a custom meal name", "danger")
        return redirect(
            url_for("meal_plan.meal_plan")
            + f"?week={request.form.get('week_offset', 0)}"
        )

    try:
        # Parse date
        date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Create meal plan entry
        entry = MealPlanEntry(
            household_id=g.household.id,
            recipe_id=int(recipe_id) if recipe_id else None,
            custom_meal_name=custom_meal_name if custom_meal_name else None,
            date=date,
            meal_type=meal_type,
            notes=notes,
        )

        db.session.add(entry)
        db.session.flush()

        if assigned_cook_ids:
            cooks = User.query.filter(User.id.in_(assigned_cook_ids)).all()
            if cooks:
                entry.assigned_cook_user_id = cooks[0].id
            for cook in cooks:
                entry.assigned_cooks.append(cook)

        db.session.commit()

        flash("Meal added to plan!", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding meal plan entry: {e}", exc_info=True)
        flash("Error adding meal to plan", "danger")

    return redirect(
        url_for("meal_plan.meal_plan") + f"?week={request.form.get('week_offset', 0)}"
    )


@meal_plan_bp.route("/meal-plan/delete/<int:entry_id>", methods=["POST"])
@require_login
def delete_meal_plan_entry(entry_id: int) -> Response:
    """
    Delete a meal plan entry.

    Args:
        entry_id: Meal plan entry ID

    Returns:
        Redirect to meal plan page
    """
    entry = MealPlanEntry.query.get_or_404(entry_id)

    if entry.household_id != g.household.id:
        flash("Unauthorized", "danger")
        return redirect(url_for("meal_plan.meal_plan"))

    week_offset = request.form.get("week_offset", 0)

    db.session.delete(entry)
    db.session.commit()

    flash("Meal removed from plan", "success")
    return redirect(url_for("meal_plan.meal_plan") + f"?week={week_offset}")


@meal_plan_bp.route("/meal-plan/add-to-list", methods=["POST"])
@require_login
def add_meal_plan_to_list() -> Response:
    """
    Add recipes from meal plan to grocery list.

    Returns:
        Redirect to homepage
    """
    if not g.household:
        flash("Please create or join a household first", "warning")
        return redirect(url_for("main.homepage"))

    # Get week offset
    week_offset = int(request.form.get("week_offset", 0))

    # Calculate week range
    today = datetime.now().date()
    days_since_monday = today.weekday()
    week_start = (
        today - timedelta(days=days_since_monday) + timedelta(weeks=week_offset)
    )
    week_end = week_start + timedelta(days=6)

    # Get all meal plan entries for this week
    meal_entries = MealPlanEntry.query.filter(
        MealPlanEntry.household_id == g.household.id,
        MealPlanEntry.date >= week_start,
        MealPlanEntry.date <= week_end,
    ).all()

    if not meal_entries:
        flash("No meals planned for this week", "warning")
        return redirect(url_for("meal_plan.meal_plan") + f"?week={week_offset}")

    # Get unique recipe IDs (filter out custom meals without recipes)
    recipe_ids = list(
        set([str(entry.recipe_id) for entry in meal_entries if entry.recipe_id])
    )

    if not recipe_ids:
        flash("No recipes found in meal plan (only custom meals)", "warning")
        return redirect(url_for("meal_plan.meal_plan") + f"?week={week_offset}")

    # Add to current grocery list
    grocery_list = g.grocery_list

    # If no grocery list exists, create one
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
        recipe_ids, grocery_list=grocery_list, user_id=g.user.id
    )

    flash(f"Added {len(recipe_ids)} recipes to grocery list!", "success")
    return redirect(url_for("main.homepage"))


@meal_plan_bp.route("/meal-plan/move/<int:entry_id>", methods=["POST"])
@require_login
def move_meal_plan_entry(entry_id: int) -> Any:
    entry = MealPlanEntry.query.get_or_404(entry_id)

    if not g.household or entry.household_id != g.household.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    payload = request.get_json(silent=True) or {}
    date_str = (payload.get("date") or request.form.get("date", "")).strip()
    meal_type = (payload.get("meal_type") or request.form.get("meal_type", "")).strip().lower()
    target_entry_id = payload.get("target_entry_id")  # ID of card being dropped onto

    if not date_str or not meal_type:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    if meal_type not in {"breakfast", "lunch", "dinner"}:
        return jsonify({"success": False, "error": "Invalid meal type"}), 400

    try:
        new_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"success": False, "error": "Invalid date format"}), 400

    old_date = entry.date
    old_meal_type = entry.meal_type

    if old_date == new_date and old_meal_type == meal_type and not target_entry_id:
        return jsonify({"success": True, "message": "No change"})

    # Check if we're swapping with another card
    if target_entry_id:
        target_entry = MealPlanEntry.query.get(target_entry_id)
        if target_entry and target_entry.household_id == g.household.id:
            # Swap the positions
            target_old_date = target_entry.date
            target_old_meal_type = target_entry.meal_type

            target_entry.date = old_date
            target_entry.meal_type = old_meal_type

            entry.date = new_date
            entry.meal_type = meal_type

            # Log both changes
            change1 = MealPlanChange(
                household_id=g.household.id,
                change_type="updated",
                meal_name=entry.meal_name,
                meal_date=entry.date,
                meal_type=entry.meal_type,
                changed_by_user_id=g.user.id,
                change_details=f"Swapped from {old_date} {old_meal_type} to {entry.date} {entry.meal_type}",
            )
            change2 = MealPlanChange(
                household_id=g.household.id,
                change_type="updated",
                meal_name=target_entry.meal_name,
                meal_date=target_entry.date,
                meal_type=target_entry.meal_type,
                changed_by_user_id=g.user.id,
                change_details=f"Swapped from {target_old_date} {target_old_meal_type} to {target_entry.date} {target_entry.meal_type}",
            )
            db.session.add(change1)
            db.session.add(change2)
            db.session.commit()

            return jsonify({"success": True, "message": "Meals swapped successfully"})

    # Regular move (no swap)
    entry.date = new_date
    entry.meal_type = meal_type

    change = MealPlanChange(
        household_id=g.household.id,
        change_type="updated",
        meal_name=entry.meal_name,
        meal_date=entry.date,
        meal_type=entry.meal_type,
        changed_by_user_id=g.user.id,
        change_details=f"Moved from {old_date} {old_meal_type} to {entry.date} {entry.meal_type}",
    )
    db.session.add(change)
    db.session.commit()

    return jsonify({"success": True, "message": "Meal moved successfully"})


@meal_plan_bp.route("/meal-plan/update/<int:entry_id>", methods=["POST"])
@require_login
def update_meal_plan_entry(entry_id: int) -> Response:
    """
    Update a meal plan entry date and/or assigned cooks.

    Args:
        entry_id: Meal plan entry ID

    Returns:
        Redirect to meal plan page
    """
    entry = MealPlanEntry.query.get_or_404(entry_id)

    if not g.household or entry.household_id != g.household.id:
        flash("Unauthorized", "danger")
        return redirect(url_for("meal_plan.meal_plan"))

    week_offset = request.form.get("week_offset", 0)
    date_str = request.form.get("date", "").strip()

    if date_str:
        try:
            entry.date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format", "danger")
            return redirect(url_for("meal_plan.meal_plan") + f"?week={week_offset}")

    cook_ids = [int(cook_id) for cook_id in request.form.getlist("assigned_cook_ids") if cook_id]
    cooks = User.query.filter(User.id.in_(cook_ids)).all() if cook_ids else []

    # Keep legacy single-cook field in sync for compatibility.
    entry.assigned_cook_user_id = cooks[0].id if cooks else None

    entry.assigned_cooks = []
    for cook in cooks:
        entry.assigned_cooks.append(cook)

    db.session.commit()
    flash("Meal plan updated", "success")
    return redirect(url_for("meal_plan.meal_plan") + f"?week={week_offset}")


def _normalize_ingredient_name(name: str) -> str:
    """Normalize ingredient text for lightweight overlap matching."""
    normalized = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (name or ""))
    return " ".join(normalized.split())


@meal_plan_bp.route("/meal-plan/similar-recipes", methods=["POST"])
@require_login
def find_similar_recipes() -> Any:
    """
    Find recipes with ingredient overlap against the current week's planned meals.

    Returns:
        JSON payload of matched recipes
    """
    if not g.household:
        return jsonify({"success": False, "error": "Please create or join a household first"}), 400

    week_offset = int(request.form.get("week_offset", 0))
    today = get_est_date()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    meal_entries = MealPlanEntry.query.filter(
        MealPlanEntry.household_id == g.household.id,
        MealPlanEntry.date >= week_start,
        MealPlanEntry.date <= week_end,
        MealPlanEntry.recipe_id.isnot(None),
    ).all()

    meal_plan_recipe_ids = {entry.recipe_id for entry in meal_entries if entry.recipe_id}
    shopping_ingredient_set = set()
    for entry in meal_entries:
        if entry.recipe and entry.recipe.recipe_ingredients:
            for ingredient in entry.recipe.recipe_ingredients:
                normalized = _normalize_ingredient_name(ingredient.ingredient_name)
                if normalized:
                    shopping_ingredient_set.add(normalized)

    if not shopping_ingredient_set:
        return jsonify({"success": True, "matched_recipes": []})

    candidate_recipes = Recipe.query.filter(
        ((Recipe.household_id == g.household.id) | ((Recipe.user_id == g.user.id) & (Recipe.household_id.is_(None))))
    ).all()

    matched_recipes = []
    for recipe in candidate_recipes:
        if recipe.id in meal_plan_recipe_ids or not recipe.recipe_ingredients:
            continue

        ingredient_payload = []
        matched_count = 0
        for ingredient in recipe.recipe_ingredients:
            ingredient_name = ingredient.ingredient_name or ""
            normalized = _normalize_ingredient_name(ingredient_name)
            is_matched = normalized in shopping_ingredient_set if normalized else False
            if is_matched:
                matched_count += 1

            display_text = " ".join(
                part
                for part in [
                    str(ingredient.quantity).rstrip("0").rstrip(".") if ingredient.quantity else "",
                    ingredient.measurement or "",
                    ingredient_name,
                ]
                if part
            ).strip()
            ingredient_payload.append(
                {"text": display_text or ingredient_name or "Unknown ingredient", "matched": is_matched}
            )

        ingredient_count = len(recipe.recipe_ingredients)
        if ingredient_count == 0:
            continue

        match_percentage = int(round((matched_count / ingredient_count) * 100))
        if match_percentage >= 25:
            matched_recipes.append(
                {
                    "id": recipe.id,
                    "name": recipe.name,
                    "match_percentage": match_percentage,
                    "ingredient_count": ingredient_count,
                    "ingredients": ingredient_payload,
                }
            )

    matched_recipes.sort(key=lambda r: r["match_percentage"], reverse=True)
    return jsonify({"success": True, "matched_recipes": matched_recipes})


@meal_plan_bp.route("/meal-plan/apply-similar-recipes", methods=["POST"])
@require_login
def apply_similar_recipes() -> Any:
    """
    Add selected similar recipes to meal plan.

    Returns:
        JSON response indicating success/failure
    """
    if not g.household:
        return jsonify({"success": False, "error": "Please create or join a household first"}), 400

    data = request.get_json(silent=True) or {}
    selected_recipes = data.get("recipes", [])

    if not selected_recipes:
        return jsonify({"success": False, "error": "No recipes selected"}), 400

    added_count = 0
    for recipe_data in selected_recipes:
        try:
            recipe_id = int(recipe_data.get("recipe_id"))
            meal_date = datetime.strptime(recipe_data.get("date", ""), "%Y-%m-%d").date()
            meal_type = (recipe_data.get("meal_type") or "").strip().lower()
            notes = (recipe_data.get("notes") or "").strip()
            assigned_cooks_raw = recipe_data.get("assigned_cooks", [])
            assigned_cook_ids = [int(cook_id) for cook_id in assigned_cooks_raw if str(cook_id).strip()]
        except (TypeError, ValueError):
            continue

        if meal_type not in {"breakfast", "lunch", "dinner", "snack"}:
            continue

        recipe = Recipe.query.filter(
            Recipe.id == recipe_id,
            ((Recipe.household_id == g.household.id) | ((Recipe.user_id == g.user.id) & (Recipe.household_id.is_(None))))
        ).first()
        if not recipe:
            continue

        entry = MealPlanEntry(
            household_id=g.household.id,
            recipe_id=recipe_id,
            date=meal_date,
            meal_type=meal_type,
            notes=notes if notes else None,
            assigned_cook_user_id=assigned_cook_ids[0] if assigned_cook_ids else None,
        )
        db.session.add(entry)
        db.session.flush()

        if assigned_cook_ids:
            cooks = User.query.filter(User.id.in_(assigned_cook_ids)).all()
            for cook in cooks:
                entry.assigned_cooks.append(cook)

        added_count += 1

    db.session.commit()
    return jsonify(
        {
            "success": True,
            "message": f"Added {added_count} recipe{'s' if added_count != 1 else ''} to meal plan!",
            "added_count": added_count,
        }
    )


@meal_plan_bp.route("/meal-plan/email", methods=["POST"])
@require_login
def send_meal_plan_email() -> Response:
    """
    Send this week's meal plan to the logged-in user's email.

    Returns:
        Redirect to meal plan page
    """
    if not g.household:
        flash("Please create or join a household first", "warning")
        return redirect(url_for("meal_plan.meal_plan"))

    if not g.user or not g.user.email:
        flash("No email address found for your account", "danger")
        return redirect(url_for("meal_plan.meal_plan"))

    week_offset = int(request.form.get("week_offset", 0))
    today = get_est_date()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    meal_entries = MealPlanEntry.query.filter(
        MealPlanEntry.household_id == g.household.id,
        MealPlanEntry.date >= week_start,
        MealPlanEntry.date <= week_end,
    ).all()

    if not meal_entries:
        flash("No meals planned for this week", "warning")
        return redirect(url_for("meal_plan.meal_plan") + f"?week={week_offset}")

    try:
        MealPlanEntry.send_meal_plan_email(
            recipient=g.user.email,
            meal_entries=meal_entries,
            user_id=g.user.id,
            week_start=week_start,
            week_end=week_end,
            mail=mail,
        )
        flash("Meal plan sent to your email!", "success")
    except Exception as e:
        logger.error(f"Error sending meal plan email: {e}", exc_info=True)
        flash("Email service is currently unavailable. Please try again later.", "danger")

    return redirect(url_for("meal_plan.meal_plan") + f"?week={week_offset}")
