"""
Pantry list management routes blueprint.

Handles pantry list CRUD operations and item management.
"""

from flask import (
    Blueprint,
    current_app,
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
from models import GroceryList, GroceryListItem, Recipe, RecipeIngredient
from utils import (
    require_login,
    CURR_GROCERY_LIST_KEY,
    parse_quantity_string,
    get_est_now,
    parse_simple_ingredient,
)
from logging_config import logger
from typing import Union

grocery_bp = Blueprint("grocery", __name__)


def _build_ingredient_label(name: str, quantity=None, measurement=None) -> str:
    """Build a user-facing ingredient label for emails and flashes."""
    ingredient_name = str(name or "ingredient").strip()

    quantity_text = ""
    if quantity not in (None, ""):
        if isinstance(quantity, float) and quantity.is_integer():
            quantity = int(quantity)
        quantity_text = str(quantity).strip()

    measurement_text = str(measurement or "").strip()
    if measurement_text.lower() == "unit":
        measurement_text = ""

    if not quantity_text and not measurement_text:
        return ingredient_name
    if not measurement_text:
        if quantity_text in ("1", "1.0"):
            return ingredient_name
        return f"{quantity_text} {ingredient_name}".strip()
    return f"{quantity_text} {measurement_text} {ingredient_name}".strip()


def _add_last_minute_items_to_grocery_list(
    grocery_list: GroceryList, last_minute_items_text: str
) -> list[str]:
    """Parse and append last-minute items to the active pantry list."""
    added_item_labels = []

    for ingredient_text in [
        line.strip() for line in last_minute_items_text.splitlines() if line.strip()
    ]:
        parsed_ingredients = Recipe.parse_ingredients(ingredient_text)
        if not parsed_ingredients:
            parsed_ingredients = parse_simple_ingredient(ingredient_text)

        for ingredient_data in parsed_ingredients:
            quantity = parse_quantity_string(str(ingredient_data.get("quantity") or ""))
            if quantity is None:
                quantity = 1.0

            measurement = ingredient_data.get("measurement") or "unit"
            ingredient_name = (
                ingredient_data.get("ingredient_name")
                or ingredient_data.get("name")
                or ingredient_text
            )

            recipe_ingredient = RecipeIngredient(
                ingredient_name=ingredient_name,
                quantity=quantity,
                measurement=measurement,
            )
            db.session.add(recipe_ingredient)
            db.session.flush()

            grocery_list_item = GroceryListItem(
                grocery_list_id=grocery_list.id,
                recipe_ingredient_id=recipe_ingredient.id,
                added_by_user_id=g.user.id,
            )
            db.session.add(grocery_list_item)
            added_item_labels.append(
                _build_ingredient_label(ingredient_name, quantity, measurement)
            )

    if added_item_labels:
        grocery_list.last_modified_by_user_id = g.user.id
        grocery_list.last_modified_at = get_est_now()

    return added_item_labels


def _get_household_notification_recipients(selected_user_ids) -> list:
    """Return valid, selected household members who can receive notifications."""
    if not g.household:
        return []

    selected_id_set = {
        int(user_id) for user_id in selected_user_ids if str(user_id).strip().isdigit()
    }
    if not selected_id_set:
        return []

    recipients = []
    for member in g.household.members:
        user = member.user
        if (
            not user
            or not user.email
            or user.id == g.user.id
            or user.id not in selected_id_set
        ):
            continue
        recipients.append(user)

    return recipients


def _send_household_shopping_started_emails(
    recipient_ids: list[str], last_minute_items: list[str]
) -> int:
    """Notify selected household members that shopping has started."""
    recipients = _get_household_notification_recipients(recipient_ids)
    if not recipients:
        return 0

    base_url = request.url_root.rstrip("/")
    response_email = current_app.config.get(
        "MAIL_DEFAULT_SENDER", "support@autocart.com"
    )
    household_name = g.household.name if g.household else "your household"
    grocery_list_name = g.grocery_list.name if g.grocery_list else "Shared Pantry List"
    subject = f"{g.user.username} started shopping for {household_name}"

    for recipient in recipients:
        html_body = render_template(
            "shopping_started_email.html",
            recipient_name=recipient.username,
            shopper_name=g.user.username,
            household_name=household_name,
            grocery_list_name=grocery_list_name,
            last_minute_items=last_minute_items,
            homepage_url=base_url,
            household_settings_url=f"{base_url}/household/settings",
        )
        text_body = (
            f"Hi {recipient.username},\n\n"
            f"{g.user.username} just started shopping for the {household_name} household.\n"
            f"Pantry list: {grocery_list_name}\n\n"
            f"Open Auto-Cart: {base_url}\n"
            f"Household settings: {base_url}/household/settings\n\n"
        )
        if last_minute_items:
            text_body += "Last-Minute Items Added:\n"
            text_body += "\n".join(f"• {item}" for item in last_minute_items)
            text_body += "\n\n"

        text_body += (
            "---\n"
            "Auto-Cart - Smart Household Grocery Management\n"
            f"For support: {response_email}"
        )
        msg = Message(
            subject=subject,
            recipients=[recipient.email],
            body=text_body,
            html=html_body,
        )
        mail.send(msg)

    logger.info(
        "Sent shopping-started notification email to %s recipients", len(recipients)
    )
    return len(recipients)


@grocery_bp.route("/update_grocery_list", methods=["POST"])
@require_login
def update_grocery_list() -> Response:
    """
    Add selected recipes to current pantry list.

    Returns:
        Redirect to homepage
    """
    selected_recipe_ids = request.form.getlist("recipe_ids")
    session["selected_recipe_ids"] = selected_recipe_ids

    grocery_list = g.grocery_list

    # If no pantry list exists, create a default one
    if not grocery_list and g.household:
        grocery_list = GroceryList(
            household_id=g.household.id,
            user_id=g.user.id,
            created_by_user_id=g.user.id,
            name="Household Pantry List",
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


@grocery_bp.route("/send-email", methods=["POST"])
@require_login
def send_grocery_list_email() -> Response:
    """Send the pantry list and selected recipes to supplied email recipients."""
    selected_user_emails = request.form.getlist("user_emails")
    custom_email = request.form.get("custom_email", "").strip()

    all_emails = list(selected_user_emails)
    if custom_email:
        all_emails.append(custom_email)

    if not all_emails:
        flash(
            "Please select at least one recipient or enter an email address",
            "danger",
        )
        return redirect(url_for("main.homepage") + "#email-modal")

    email_type = request.form.get("email_type", "list_and_recipes")
    selected_recipe_ids = request.form.getlist("recipe_ids")
    grocery_list = g.grocery_list

    try:
        for email in all_emails:
            if email_type == "recipes_only":
                GroceryList.send_recipes_only_email(email, selected_recipe_ids, mail)
                continue

            if not grocery_list:
                flash("No pantry list found", "error")
                return redirect(url_for("main.homepage"))

            GroceryList.send_email(email, grocery_list, selected_recipe_ids, mail)

        recipient_count = len(all_emails)
        if email_type == "recipes_only":
            flash(
                f"Recipes sent successfully to {recipient_count} recipient(s)!",
                "success",
            )
        else:
            flash(
                f"Pantry list sent successfully to {recipient_count} recipient(s)!",
                "success",
            )
    except Exception as e:
        logger.error(f"Email error: {e}", exc_info=True)
        flash(
            "Email service is currently unavailable. Please try again later.",
            "danger",
        )

    return redirect(url_for("main.homepage"))


@grocery_bp.route("/grocery-list/create", methods=["POST"])
@require_login
def create_grocery_list() -> Response:
    """
    Create a new pantry list for the household.

    Returns:
        Redirect to homepage
    """
    if not g.household:
        flash("You must be in a household to create a pantry list", "danger")
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

    flash(f'Pantry list "{list_name}" created successfully!', "success")
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/grocery-list/switch/<int:list_id>", methods=["POST"])
@require_login
def switch_grocery_list(list_id: int) -> Response:
    """
    Switch to a different pantry list.

    Args:
        list_id: Pantry list ID

    Returns:
        Redirect to homepage
    """
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id, household_id=g.household.id
    ).first()

    if not grocery_list:
        flash("Pantry list not found", "danger")
        return redirect(url_for("main.homepage"))

    session[CURR_GROCERY_LIST_KEY] = list_id
    flash(f'Switched to "{grocery_list.name}"', "success")
    return redirect(url_for("main.homepage"))


@grocery_bp.route("/grocery-list/rename/<int:list_id>", methods=["POST"])
@require_login
def rename_grocery_list(list_id: int) -> Response:
    """
    Rename a pantry list.

    Args:
        list_id: Pantry list ID

    Returns:
        Redirect to homepage
    """
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id, household_id=g.household.id
    ).first()

    if not grocery_list:
        flash("Pantry list not found", "danger")
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
    Delete a pantry list.

    Args:
        list_id: Pantry list ID

    Returns:
        Redirect to homepage
    """
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id, household_id=g.household.id
    ).first()

    if not grocery_list:
        flash("Pantry list not found", "danger")
        return redirect(url_for("main.homepage"))

    # Don't allow deleting the last list
    all_lists = GroceryList.query.filter_by(household_id=g.household.id).all()
    if len(all_lists) <= 1:
        flash("Cannot delete the last pantry list", "danger")
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
    Clear all items from the current pantry list.

    Returns:
        Redirect to homepage
    """
    grocery_list = g.grocery_list

    if grocery_list:
        # Delete all pantry list items
        for item in grocery_list.items:
            db.session.delete(item)
        db.session.commit()
        flash("Pantry list cleared successfully!", "success")
    else:
        flash("No pantry list found", "error")

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
        flash("Please select a pantry list first", "warning")
        return redirect(url_for("main.homepage"))

    grocery_list = g.grocery_list

    # Get all items with their ingredients
    items = GroceryListItem.query.filter_by(grocery_list_id=grocery_list.id).all()

    # Calculate progress
    total_items = len(items)
    checked_items = sum(1 for item in items if item.is_checked)
    household_members = []
    if g.household:
        household_members = sorted(
            [
                member
                for member in g.household.members
                if member.user and member.user.email and member.user.id != g.user.id
            ],
            key=lambda member: member.user.username.lower(),
        )

    return render_template(
        "shopping_mode.html",
        grocery_list=grocery_list,
        items=items,
        total_items=total_items,
        checked_items=checked_items,
        household_members=household_members,
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
        flash("Please select a pantry list first", "warning")
        return redirect(url_for("main.homepage"))

    grocery_list = g.grocery_list
    recipient_ids = request.form.getlist("email_recipient_ids")
    last_minute_items_text = request.form.get("last_minute_items", "").strip()

    try:
        added_last_minute_items = _add_last_minute_items_to_grocery_list(
            grocery_list, last_minute_items_text
        )
        grocery_list.status = "shopping"
        grocery_list.shopping_user_id = g.user.id
        grocery_list.last_modified_by_user_id = g.user.id
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error starting shopping session: {e}", exc_info=True)
        flash("Could not start shopping session. Please try again.", "danger")
        return redirect(url_for("grocery.shopping_mode"))

    emails_sent = 0
    if recipient_ids:
        try:
            emails_sent = _send_household_shopping_started_emails(
                recipient_ids, added_last_minute_items
            )
        except Exception as e:
            logger.error(
                f"Error sending shopping-start notification emails: {e}",
                exc_info=True,
            )
            flash(
                "Shopping session started, but email notifications could not be sent.",
                "warning",
            )

    success_parts = ["Shopping session started!"]
    if added_last_minute_items:
        success_parts.append(
            f"Added {len(added_last_minute_items)} last-minute item(s)."
        )
    if recipient_ids and emails_sent:
        success_parts.append(f"Notified {emails_sent} household member(s) by email.")

    flash(" ".join(success_parts), "success")
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
        flash("Please select a pantry list first", "warning")
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
        item_id: Pantry list item ID

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
