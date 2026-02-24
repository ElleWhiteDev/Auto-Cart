"""
Meal planning routes blueprint.

Handles meal plan CRUD operations and email notifications.
"""

import os
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
from flask_mail import Message
from werkzeug.wrappers import Response

from extensions import db, mail
from models import (
    MealPlanEntry,
    GroceryList,
    Recipe,
    User,
    MealPlanChange,
    HouseholdMember,
    Household,
)
from utils import require_login, CURR_GROCERY_LIST_KEY, get_est_date
from logging_config import logger
from typing import Union, Dict, Any, Tuple

meal_plan_bp = Blueprint("meal_plan", __name__)


# Email notification helper functions
def send_chef_assigned_to_meal_email(
    recipient_email: str,
    recipient_name: str,
    meal_name: str,
    meal_date,
    meal_type: str,
    household_name: str,
    assigned_by_name: str,
) -> None:
    """Send email to chef when they're assigned to cook a meal"""
    # Get admin email from config or use default sender
    admin_email = mail.default_sender or "support@autocart.com"

    # Build meal plan URL
    base_url = request.url_root.rstrip("/")
    meal_plan_url = f"{base_url}/meal-plan"

    # Format the date nicely
    if isinstance(meal_date, str):
        meal_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
    formatted_date = meal_date.strftime("%A, %B %d, %Y")

    subject = f"You've been assigned to cook {meal_name} on {formatted_date}"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #27AE60; color: white; padding: 20px; text-align: center; }}
        .content {{ background-color: #f9f9f9; padding: 20px; }}
        .meal-details {{ background-color: white; padding: 15px; margin: 15px 0; border-left: 4px solid #27AE60; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #4A90E2; color: white !important; text-decoration: none; border-radius: 4px; margin: 15px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>👨‍🍳 You're Cooking!</h1>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <p><strong>{assigned_by_name}</strong> has assigned you to cook the following meal in the <strong>{household_name}</strong> household:</p>

            <div class="meal-details">
                <p><strong>Meal:</strong> {meal_name}</p>
                <p><strong>Date:</strong> {formatted_date}</p>
                <p><strong>Type:</strong> {meal_type.capitalize()}</p>
            </div>

            <p>Check the meal plan to see the recipe details and start planning!</p>

            <a href="{meal_plan_url}" class="button">View Meal Plan</a>
        </div>
        <div class="footer">
            <p>Auto-Cart - Smart Household Grocery Management</p>
            <p>For support: {admin_email}</p>
        </div>
    </div>
</body>
</html>
    """

    text_body = f"""
You're Cooking!

Hi {recipient_name},

{assigned_by_name} has assigned you to cook the following meal in the {household_name} household:

Meal: {meal_name}
Date: {formatted_date}
Type: {meal_type.capitalize()}

Check the meal plan to see the recipe details and start planning!

View your meal plan: {meal_plan_url}

---
Auto-Cart - Smart Household Grocery Management
For support: {admin_email}
    """

    msg = Message(
        subject=subject, recipients=[recipient_email], body=text_body, html=html_body
    )

    mail.send(msg)
    logger.info(
        f"Chef assigned email sent to {recipient_email} for meal {meal_name} on {meal_date}"
    )


def send_chef_removed_from_meal_email(
    recipient_email: str,
    recipient_name: str,
    meal_name: str,
    meal_date,
    meal_type: str,
    household_name: str,
) -> None:
    """Send email to chef when they're removed from a meal plan entry"""
    # Get admin email from config or use default sender
    admin_email = mail.default_sender or "support@autocart.com"

    # Build meal plan URL
    base_url = request.url_root.rstrip("/")
    meal_plan_url = f"{base_url}/meal-plan"

    # Format the date nicely
    if isinstance(meal_date, str):
        meal_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
    formatted_date = meal_date.strftime("%A, %B %d, %Y")

    subject = f"You've been removed from cooking {meal_name} on {formatted_date}"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4A90E2; color: white; padding: 20px; text-align: center; }}
        .content {{ background-color: #f9f9f9; padding: 20px; }}
        .meal-details {{ background-color: white; padding: 15px; margin: 15px 0; border-left: 4px solid #4A90E2; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #4A90E2; color: white !important; text-decoration: none; border-radius: 4px; margin: 15px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🍳 Chef Assignment Update</h1>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <p>You've been removed from cooking the following meal in the <strong>{household_name}</strong> household:</p>

            <div class="meal-details">
                <p><strong>Meal:</strong> {meal_name}</p>
                <p><strong>Date:</strong> {formatted_date}</p>
                <p><strong>Type:</strong> {meal_type.capitalize()}</p>
            </div>

            <p>This change was made by another household member. If you have questions, please check with your household.</p>

            <a href="{meal_plan_url}" class="button">View Meal Plan</a>
        </div>
        <div class="footer">
            <p>Auto-Cart - Smart Household Grocery Management</p>
            <p>For support: {admin_email}</p>
        </div>
    </div>
</body>
</html>
    """

    text_body = f"""
Chef Assignment Update

Hi {recipient_name},

You've been removed from cooking the following meal in the {household_name} household:

Meal: {meal_name}
Date: {formatted_date}
Type: {meal_type.capitalize()}

This change was made by another household member. If you have questions, please check with your household.

View your meal plan: {meal_plan_url}

---
Auto-Cart - Smart Household Grocery Management
For support: {admin_email}
    """

    msg = Message(
        subject=subject, recipients=[recipient_email], body=text_body, html=html_body
    )

    mail.send(msg)
    logger.info(
        f"Chef removed email sent to {recipient_email} for meal {meal_name} on {meal_date}"
    )


def send_meal_deleted_email(
    recipient_email: str,
    recipient_name: str,
    meal_name: str,
    meal_date,
    meal_type: str,
    household_name: str,
) -> None:
    """Send email to chef when a meal they're assigned to is deleted from the plan"""
    # Get admin email from config or use default sender
    admin_email = mail.default_sender or "support@autocart.com"

    # Build meal plan URL
    base_url = request.url_root.rstrip("/")
    meal_plan_url = f"{base_url}/meal-plan"

    # Format the date nicely
    if isinstance(meal_date, str):
        meal_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
    formatted_date = meal_date.strftime("%A, %B %d, %Y")

    subject = f"Meal removed from plan: {meal_name} on {formatted_date}"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #E74C3C; color: white; padding: 20px; text-align: center; }}
        .content {{ background-color: #f9f9f9; padding: 20px; }}
        .meal-details {{ background-color: white; padding: 15px; margin: 15px 0; border-left: 4px solid #E74C3C; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #4A90E2; color: white !important; text-decoration: none; border-radius: 4px; margin: 15px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🗑️ Meal Removed from Plan</h1>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <p>A meal you were assigned to cook has been removed from the <strong>{household_name}</strong> meal plan:</p>

            <div class="meal-details">
                <p><strong>Meal:</strong> {meal_name}</p>
                <p><strong>Date:</strong> {formatted_date}</p>
                <p><strong>Type:</strong> {meal_type.capitalize()}</p>
            </div>

            <p>This meal has been deleted from the plan by another household member.</p>

            <a href="{meal_plan_url}" class="button">View Meal Plan</a>
        </div>
        <div class="footer">
            <p>Auto-Cart - Smart Household Grocery Management</p>
            <p>For support: {admin_email}</p>
        </div>
    </div>
</body>
</html>
    """

    text_body = f"""
Meal Removed from Plan

Hi {recipient_name},

A meal you were assigned to cook has been removed from the {household_name} meal plan:

Meal: {meal_name}
Date: {formatted_date}
Type: {meal_type.capitalize()}

This meal has been deleted from the plan by another household member.

View your meal plan: {meal_plan_url}

---
Auto-Cart - Smart Household Grocery Management
For support: {admin_email}
    """

    msg = Message(
        subject=subject, recipients=[recipient_email], body=text_body, html=html_body
    )

    mail.send(msg)
    logger.info(
        f"Meal deleted email sent to {recipient_email} for meal {meal_name} on {meal_date}"
    )


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

    # Convert recipe_id to int or None (handle 'custom' value)
    if recipe_id and recipe_id != "custom":
        try:
            recipe_id = int(recipe_id)
        except ValueError:
            recipe_id = None
    else:
        recipe_id = None

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
            recipe_id=recipe_id,
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

        # Track the change for daily summary
        change = MealPlanChange(
            household_id=g.household.id,
            change_type="added",
            meal_name=entry.meal_name,
            meal_date=entry.date,
            meal_type=entry.meal_type,
            changed_by_user_id=g.user.id,
        )
        db.session.add(change)

        db.session.commit()

        # Send email notifications to assigned chefs
        # Only notify if they were assigned by a different user
        if assigned_cook_ids:
            cooks = User.query.filter(User.id.in_(assigned_cook_ids)).all()
            for cook in cooks:
                # Skip if the cook assigned themselves
                if cook.id == g.user.id:
                    continue

                if cook.email:
                    # Check if the cook has chef assignment emails enabled for this household
                    member = HouseholdMember.query.filter_by(
                        household_id=g.household.id, user_id=cook.id
                    ).first()

                    if member and member.receive_chef_assignment_emails:
                        try:
                            send_chef_assigned_to_meal_email(
                                recipient_email=cook.email,
                                recipient_name=cook.username,
                                meal_name=entry.meal_name,
                                meal_date=entry.date,
                                meal_type=entry.meal_type,
                                household_name=g.household.name,
                                assigned_by_name=g.user.username,
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send chef assigned email to {cook.email}: {e}"
                            )

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

    # Send email notifications to assigned chefs before deleting
    # Only notify if the change is made by a different user
    if entry.assigned_cooks:
        for cook in entry.assigned_cooks:
            # Skip if the cook is the one making the change
            if cook.id == g.user.id:
                continue

            if cook.email:
                # Check if the cook has chef assignment emails enabled for this household
                member = HouseholdMember.query.filter_by(
                    household_id=g.household.id, user_id=cook.id
                ).first()

                if member and member.receive_chef_assignment_emails:
                    try:
                        send_meal_deleted_email(
                            recipient_email=cook.email,
                            recipient_name=cook.username,
                            meal_name=entry.meal_name,
                            meal_date=entry.date,
                            meal_type=entry.meal_type,
                            household_name=g.household.name,
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send meal deleted email to {cook.email}: {e}"
                        )

    # Track the change for daily summary
    change = MealPlanChange(
        household_id=g.household.id,
        change_type="deleted",
        meal_name=entry.meal_name,
        meal_date=entry.date,
        meal_type=entry.meal_type,
        changed_by_user_id=g.user.id,
    )
    db.session.add(change)

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

    # Get the new list of assigned cook IDs from the form
    new_cook_ids = [
        int(cook_id) for cook_id in request.form.getlist("assigned_cook_ids") if cook_id
    ]

    # Get current assigned cooks
    current_cooks = set(entry.assigned_cooks)
    current_cook_ids = {cook.id for cook in current_cooks}

    # Find removed cooks (those who were assigned but are no longer)
    removed_cook_ids = current_cook_ids - set(new_cook_ids)
    removed_cooks = [cook for cook in current_cooks if cook.id in removed_cook_ids]

    # Send emails to removed chefs who have opted in
    # Only notify if the change is made by a different user
    for cook in removed_cooks:
        # Skip if the cook is the one making the change (removing themselves)
        if cook.id == g.user.id:
            continue

        if cook.email:
            # Check if the cook has chef assignment emails enabled for this household
            member = HouseholdMember.query.filter_by(
                household_id=g.household.id, user_id=cook.id
            ).first()

            if member and member.receive_chef_assignment_emails:
                try:
                    send_chef_removed_from_meal_email(
                        recipient_email=cook.email,
                        recipient_name=cook.username,
                        meal_name=entry.meal_name,
                        meal_date=entry.date,
                        meal_type=entry.meal_type,
                        household_name=g.household.name,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send chef removed email to {cook.email}: {e}"
                    )

    # Find newly added cooks (those who weren't assigned before)
    added_cook_ids = set(new_cook_ids) - current_cook_ids

    # Update the assigned cooks
    cooks = User.query.filter(User.id.in_(new_cook_ids)).all() if new_cook_ids else []

    # Keep legacy single-cook field in sync for compatibility.
    entry.assigned_cook_user_id = cooks[0].id if cooks else None

    entry.assigned_cooks = []
    for cook in cooks:
        entry.assigned_cooks.append(cook)

    db.session.commit()

    # Send emails to newly added chefs who have opted in
    # Only notify if they were assigned by a different user
    if added_cook_ids:
        added_cooks = User.query.filter(User.id.in_(added_cook_ids)).all()
        for cook in added_cooks:
            # Skip if the cook assigned themselves
            if cook.id == g.user.id:
                continue

            if cook.email:
                # Check if the cook has chef assignment emails enabled for this household
                member = HouseholdMember.query.filter_by(
                    household_id=g.household.id, user_id=cook.id
                ).first()

                if member and member.receive_chef_assignment_emails:
                    try:
                        send_chef_assigned_to_meal_email(
                            recipient_email=cook.email,
                            recipient_name=cook.username,
                            meal_name=entry.meal_name,
                            meal_date=entry.date,
                            meal_type=entry.meal_type,
                            household_name=g.household.name,
                            assigned_by_name=g.user.username,
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send chef assigned email to {cook.email}: {e}"
                        )

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


@meal_plan_bp.route("/meal-plan/send-daily-summaries", methods=["POST"])
def send_daily_meal_plan_summaries() -> Tuple[Dict[str, Any], int]:
    """
    Send daily meal plan summaries for all households with changes.

    This endpoint should be called by a cron job once per day.
    For security, it requires a secret token in the request.

    Returns:
        JSON response with results
    """
    # Check for authorization token
    auth_token = request.headers.get("X-Cron-Token") or request.form.get("cron_token")
    expected_token = os.environ.get("CRON_SECRET_TOKEN")

    if not expected_token or auth_token != expected_token:
        logger.warning("Unauthorized attempt to send daily meal plan summaries")
        return jsonify({"error": "Unauthorized"}), 401

    # Get all households with unemailed changes
    households_with_changes = (
        db.session.query(MealPlanChange.household_id)
        .filter_by(emailed=False)
        .distinct()
        .all()
    )

    household_ids = [h[0] for h in households_with_changes]

    if not household_ids:
        logger.info("No households with unemailed meal plan changes")
        return jsonify({"message": "No changes to email"}), 200

    results = []
    for household_id in household_ids:
        try:
            household = Household.query.get(household_id)
            if not household:
                logger.warning(f"Household {household_id} not found")
                continue

            # Get all unemailed changes for this household
            changes = (
                MealPlanChange.query.filter_by(household_id=household_id, emailed=False)
                .order_by(MealPlanChange.created_at)
                .all()
            )

            if not changes:
                continue

            # Group changes by type
            added = [c for c in changes if c.change_type == "added"]
            updated = [c for c in changes if c.change_type == "updated"]
            deleted = [c for c in changes if c.change_type == "deleted"]

            # Send email to household members who have opted in
            members = HouseholdMember.query.filter_by(
                household_id=household_id, receive_meal_plan_emails=True
            ).all()

            sent_count = 0
            for member in members:
                if member.user.email:
                    try:
                        _send_meal_plan_summary_email(
                            recipient_email=member.user.email,
                            recipient_name=member.user.username,
                            household_name=household.name,
                            added_changes=added,
                            updated_changes=updated,
                            deleted_changes=deleted,
                        )
                        sent_count += 1
                        logger.info(
                            f"Meal plan summary sent to {member.user.email} for household {household.name}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send meal plan summary to {member.user.email}: {e}"
                        )

            # Mark all changes as emailed
            for change in changes:
                change.emailed = True

            db.session.commit()

            results.append(
                {
                    "household_id": household_id,
                    "household_name": household.name,
                    "status": "success",
                    "emails_sent": sent_count,
                    "changes_count": len(changes),
                }
            )

        except Exception as e:
            logger.error(
                f"Error sending meal plan summary for household {household_id}: {e}",
                exc_info=True,
            )
            results.append(
                {
                    "household_id": household_id,
                    "status": "error",
                    "error": str(e),
                }
            )

    logger.info(f"Daily meal plan summaries sent for {len(results)} households")
    return jsonify({"message": "Summaries sent", "results": results}), 200


def _send_meal_plan_summary_email(
    recipient_email: str,
    recipient_name: str,
    household_name: str,
    added_changes: list,
    updated_changes: list,
    deleted_changes: list,
) -> None:
    """Send a daily summary email of meal plan changes"""
    # Get admin email from config or use default sender
    admin_email = mail.default_sender or "support@autocart.com"

    # Build meal plan URL
    base_url = request.url_root.rstrip("/")
    meal_plan_url = f"{base_url}/meal-plan"

    subject = f"Meal Plan Updates for {household_name}"

    # Build HTML email body
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4A90E2; color: white; padding: 20px; text-align: center; }}
        .content {{ background-color: #f9f9f9; padding: 20px; }}
        .section {{ margin: 20px 0; }}
        .section-title {{ font-size: 18px; font-weight: bold; color: #4A90E2; margin-bottom: 10px; }}
        .change-item {{ background-color: white; padding: 12px; margin: 8px 0; border-left: 4px solid #4A90E2; }}
        .change-added {{ border-left-color: #27AE60; }}
        .change-updated {{ border-left-color: #F39C12; }}
        .change-deleted {{ border-left-color: #E74C3C; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #4A90E2; color: white !important; text-decoration: none; border-radius: 4px; margin: 15px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📅 Meal Plan Updates</h1>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <p>Here's a summary of recent changes to the <strong>{household_name}</strong> meal plan:</p>
    """

    # Added meals
    if added_changes:
        html_body += f"""
            <div class="section">
                <div class="section-title">✅ Meals Added ({len(added_changes)})</div>
        """
        for change in added_changes:
            changed_by = User.query.get(change.changed_by_user_id)
            changed_by_name = changed_by.username if changed_by else "Unknown"
            formatted_date = change.meal_date.strftime("%A, %B %d")
            html_body += f"""
                <div class="change-item change-added">
                    <strong>{change.meal_name}</strong><br>
                    {formatted_date} - {change.meal_type.capitalize()}<br>
                    <small>Added by {changed_by_name}</small>
                </div>
            """
        html_body += "</div>"

    # Updated meals
    if updated_changes:
        html_body += f"""
            <div class="section">
                <div class="section-title">✏️ Meals Updated ({len(updated_changes)})</div>
        """
        for change in updated_changes:
            changed_by = User.query.get(change.changed_by_user_id)
            changed_by_name = changed_by.username if changed_by else "Unknown"
            formatted_date = change.meal_date.strftime("%A, %B %d")
            details = change.change_details or "Updated"
            html_body += f"""
                <div class="change-item change-updated">
                    <strong>{change.meal_name}</strong><br>
                    {formatted_date} - {change.meal_type.capitalize()}<br>
                    <small>{details} by {changed_by_name}</small>
                </div>
            """
        html_body += "</div>"

    # Deleted meals
    if deleted_changes:
        html_body += f"""
            <div class="section">
                <div class="section-title">❌ Meals Removed ({len(deleted_changes)})</div>
        """
        for change in deleted_changes:
            changed_by = User.query.get(change.changed_by_user_id)
            changed_by_name = changed_by.username if changed_by else "Unknown"
            formatted_date = change.meal_date.strftime("%A, %B %d")
            html_body += f"""
                <div class="change-item change-deleted">
                    <strong>{change.meal_name}</strong><br>
                    {formatted_date} - {change.meal_type.capitalize()}<br>
                    <small>Removed by {changed_by_name}</small>
                </div>
            """
        html_body += "</div>"

    html_body += f"""
            <a href="{meal_plan_url}" class="button">View Meal Plan</a>
        </div>
        <div class="footer">
            <p>Auto-Cart - Smart Household Grocery Management</p>
            <p>For support: {admin_email}</p>
        </div>
    </div>
</body>
</html>
    """

    # Build text email body
    text_body = f"""
Meal Plan Updates for {household_name}

Hi {recipient_name},

Here's a summary of recent changes to the {household_name} meal plan:
"""

    if added_changes:
        text_body += f"\n✅ MEALS ADDED ({len(added_changes)}):\n"
        for change in added_changes:
            changed_by = User.query.get(change.changed_by_user_id)
            changed_by_name = changed_by.username if changed_by else "Unknown"
            formatted_date = change.meal_date.strftime("%A, %B %d")
            text_body += f"  • {change.meal_name} - {formatted_date} ({change.meal_type.capitalize()}) - Added by {changed_by_name}\n"

    if updated_changes:
        text_body += f"\n✏️ MEALS UPDATED ({len(updated_changes)}):\n"
        for change in updated_changes:
            changed_by = User.query.get(change.changed_by_user_id)
            changed_by_name = changed_by.username if changed_by else "Unknown"
            formatted_date = change.meal_date.strftime("%A, %B %d")
            details = change.change_details or "Updated"
            text_body += f"  • {change.meal_name} - {formatted_date} ({change.meal_type.capitalize()}) - {details} by {changed_by_name}\n"

    if deleted_changes:
        text_body += f"\n❌ MEALS REMOVED ({len(deleted_changes)}):\n"
        for change in deleted_changes:
            changed_by = User.query.get(change.changed_by_user_id)
            changed_by_name = changed_by.username if changed_by else "Unknown"
            formatted_date = change.meal_date.strftime("%A, %B %d")
            text_body += f"  • {change.meal_name} - {formatted_date} ({change.meal_type.capitalize()}) - Removed by {changed_by_name}\n"

    text_body += f"""
View your meal plan: {meal_plan_url}

---
Auto-Cart - Smart Household Grocery Management
For support: {admin_email}
    """

    msg = Message(
        subject=subject, recipients=[recipient_email], body=text_body, html=html_body
    )

    mail.send(msg)
    logger.info(f"Meal plan summary email sent to {recipient_email}")
