"""
Kroger API integration routes blueprint.

Handles Kroger authentication, product search, and cart management.
"""

from collections import Counter

from flask import (
    Blueprint,
    request,
    flash,
    redirect,
    url_for,
    g,
    session,
    current_app,
    render_template,
)
from flask_mail import Message
from werkzeug.wrappers import Response

from extensions import db, mail
from models import User
from utils import require_login
from logging_config import logger

kroger_bp = Blueprint("kroger", __name__)


def _get_household_kroger_user() -> User:
    """Return the Kroger-connected user for the current household."""
    kroger_user = g.user
    if g.household and g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)
    return kroger_user


def _build_send_to_cart_resume_url() -> str:
    """Build the send-to-cart URL that should be resumed after auth."""
    route_values = {}
    if request.args.get("confirmed"):
        route_values["confirmed"] = "true"
    if request.args.get("remove_added"):
        route_values["remove_added"] = "true"
    recipient_ids = [
        recipient_id
        for recipient_id in request.args.getlist("email_recipient_ids")
        if recipient_id
    ]
    if recipient_ids:
        route_values["email_recipient_ids"] = recipient_ids
    if request.args.get("include_grocery_list"):
        route_values["include_grocery_list"] = "true"
    return url_for("kroger.kroger_send_to_cart", **route_values)


def _get_household_notification_recipients(selected_user_ids) -> list[User]:
    """Return the selected household members who should receive a Kroger order notification."""
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


def _build_grocery_list_email_items() -> list[str]:
    """Return the current pantry list items as user-facing labels."""
    if not g.grocery_list:
        return []

    grocery_items = []
    for item in g.grocery_list.items:
        ingredient = item.recipe_ingredient
        if not ingredient:
            continue
        grocery_items.append(
            _build_ingredient_label(
                ingredient.ingredient_name,
                ingredient.quantity,
                ingredient.measurement,
            )
        )

    return grocery_items


def _send_household_kroger_order_created_emails(
    recipient_ids: list[int],
    removed_exported_items: bool,
    include_grocery_list: bool,
    grocery_list_items: list[str],
    skipped_items: list[str],
) -> int:
    """Notify selected household members that a Kroger pickup order was created."""
    recipients = _get_household_notification_recipients(recipient_ids)
    if not recipients:
        return 0

    base_url = request.url_root.rstrip("/")
    response_email = current_app.config.get(
        "MAIL_DEFAULT_SENDER", "support@autocart.com"
    )
    household_name = g.household.name if g.household else "your household"
    grocery_list_name = g.grocery_list.name if g.grocery_list else "Shared Pantry List"
    grocery_list_status = (
        "Exported pantry list items were removed after the send."
        if removed_exported_items
        else "The household pantry list was left unchanged after the send."
    )
    include_grocery_list_in_email = include_grocery_list and bool(grocery_list_items)
    subject = f"Kroger pickup order created for {household_name}"

    for recipient in recipients:
        html_body = render_template(
            "kroger_pickup_order_created_email.html",
            recipient_name=recipient.username,
            created_by_name=g.user.username,
            household_name=household_name,
            grocery_list_name=grocery_list_name,
            grocery_list_status=grocery_list_status,
            include_grocery_list=include_grocery_list,
            grocery_list_items=grocery_list_items,
            skipped_items=skipped_items,
            homepage_url=base_url,
            household_settings_url=f"{base_url}/household/settings",
        )
        text_body = (
            f"Hi {recipient.username},\n\n"
            f"{g.user.username} created a Kroger pickup order for the {household_name} household.\n"
            f"Pantry list: {grocery_list_name}\n"
            f"Status: {grocery_list_status}\n\n"
            f"Open Auto-Cart: {base_url}\n"
            f"Household settings: {base_url}/household/settings\n\n"
        )
        if include_grocery_list_in_email:
            text_body += "Pantry List Items:\n"
            text_body += "\n".join(f"• {item}" for item in grocery_list_items)
            text_body += "\n\n"
        elif include_grocery_list:
            text_body += "Pantry List Items:\nThe pantry list is currently empty.\n\n"

        if skipped_items:
            text_body += "Skipped Items:\n"
            text_body += "\n".join(f"• {item}" for item in skipped_items)
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
        "Sent Kroger pickup order notification email to %s recipients", len(recipients)
    )
    return len(recipients)


def _normalize_ingredient_value(value) -> str:
    """Normalize ingredient fields for display and matching."""
    if value in (None, ""):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _build_ingredient_label(name: str, quantity=None, measurement=None) -> str:
    """Build a user-facing ingredient label."""
    parts = [
        _normalize_ingredient_value(quantity),
        _normalize_ingredient_value(measurement),
        _normalize_ingredient_value(name),
    ]
    return " ".join(part for part in parts if part)


def _remove_exported_items_from_grocery_list(
    skipped_item_ids: list[int], skipped_ingredients: list[str]
) -> None:
    """Remove exported items from the pantry list, keeping skipped items when possible."""
    if not g.grocery_list:
        return

    kept_item_ids = {
        int(item_id) for item_id in skipped_item_ids if item_id is not None
    }
    remaining_skipped_labels = Counter(
        ingredient.strip()
        for ingredient in skipped_ingredients
        if ingredient and ingredient.strip()
    )

    removed_any = False
    for item in list(g.grocery_list.items):
        ingredient = item.recipe_ingredient
        item_label = _build_ingredient_label(
            ingredient.ingredient_name,
            ingredient.quantity,
            ingredient.measurement,
        )

        if item.id in kept_item_ids:
            if remaining_skipped_labels[item_label] > 0:
                remaining_skipped_labels[item_label] -= 1
            continue

        if remaining_skipped_labels[item_label] > 0:
            remaining_skipped_labels[item_label] -= 1
            continue

        db.session.delete(item)
        removed_any = True

    if removed_any:
        g.grocery_list.last_modified_by_user_id = g.user.id
        session.pop("selected_recipe_ids", None)
        db.session.commit()


def _store_kroger_recovery_prompt(
    title: str,
    message: str,
    primary_label: str,
    primary_url: str,
    secondary_label: str = None,
    secondary_url: str = None,
) -> None:
    """Store a persistent homepage recovery prompt for Kroger actions."""
    prompt = {
        "title": title,
        "message": message,
        "primary_label": primary_label,
        "primary_url": primary_url,
    }
    if secondary_label and secondary_url:
        prompt["secondary_label"] = secondary_label
        prompt["secondary_url"] = secondary_url
    session["kroger_recovery_prompt"] = prompt


def _queue_send_to_cart_reconnect_prompt(message: str) -> None:
    """Queue a reconnect prompt while preserving current cart selections."""
    session["kroger_post_auth_redirect"] = _build_send_to_cart_resume_url()
    _store_kroger_recovery_prompt(
        "Reconnect Kroger to finish sending your cart",
        message,
        "Reconnect Kroger",
        url_for("kroger.kroger_authenticate", resume="send-to-cart"),
        "Household Settings",
        url_for("main.household_settings"),
    )


def _clear_kroger_flow_session(kroger_session_manager=None) -> None:
    """Clear in-progress Kroger flow state and any recovery prompt."""
    kroger_session_manager = kroger_session_manager or current_app.config.get(
        "kroger_session_manager"
    )

    if kroger_session_manager:
        kroger_session_manager.clear_kroger_session_data()
    else:
        for key in [
            "products_for_cart",
            "items_to_choose_from",
            "location_id",
            "stores",
            "ingredient_details",
            "current_ingredient_detail",
            "skipped_ingredients",
            "skipped_grocery_list_item_ids",
        ]:
            session.pop(key, None)
        session["show_modal"] = False

    session.pop("kroger_recovery_prompt", None)
    session.pop("kroger_post_auth_redirect", None)


@kroger_bp.route("/dismiss-recovery-prompt", methods=["POST"])
@require_login
def dismiss_recovery_prompt() -> Response:
    """Dismiss the homepage recovery prompt and exit the current Kroger flow."""
    _clear_kroger_flow_session()
    return redirect(url_for("main.homepage"))


@kroger_bp.route("/authenticate")
@require_login
def kroger_authenticate() -> Response:
    """
    Redirect user to Kroger API for authentication.

    Returns:
        Redirect to Kroger OAuth page or homepage on error
    """
    try:
        # Get Kroger services from app config
        kroger_session_manager = current_app.config.get("kroger_session_manager")
        kroger_workflow = current_app.config.get("kroger_workflow")

        if not kroger_session_manager or not kroger_workflow:
            flash("Kroger integration not configured", "danger")
            return redirect(url_for("main.homepage"))

        success_redirect_url = None
        if request.args.get("resume") == "send-to-cart":
            success_redirect_url = session.get(
                "kroger_post_auth_redirect",
                url_for("kroger.kroger_send_to_cart", confirmed="true"),
            )
        else:
            kroger_session_manager.clear_kroger_session_data()

        result = kroger_workflow.handle_authentication(
            g.user,
            current_app.config["OAUTH2_BASE_URL"],
            current_app.config["REDIRECT_URL"],
            success_redirect_url=success_redirect_url,
        )
        # If we're redirecting back to our own app (valid token), trigger the modal
        if not result.startswith("http"):
            session["open_modal"] = "modal-zipcode"
        return redirect(result)
    except Exception as e:
        logger.error(f"Kroger authentication error: {e}", exc_info=True)
        flash("Authentication error. Please try again.", "danger")
        return redirect(url_for("main.homepage"))


@kroger_bp.route("/callback")
@require_login
def callback() -> Response:
    """
    Receive bearer token and profile ID from Kroger API.

    Returns:
        Redirect to homepage with modal
    """
    authorization_code = request.args.get("code")
    error = request.args.get("error")

    if error:
        flash(f"Kroger authorization failed: {error}", "danger")
        return redirect(url_for("main.homepage"))

    if not authorization_code:
        flash("No authorization code received from Kroger", "danger")
        return redirect(url_for("main.homepage"))

    kroger_workflow = current_app.config.get("kroger_workflow")
    if not kroger_workflow:
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    success = kroger_workflow.handle_callback(
        authorization_code, g.user, current_app.config["REDIRECT_URL"]
    )

    if success:
        db.session.commit()
        post_auth_redirect = session.pop("kroger_post_auth_redirect", None)
        session.pop("kroger_recovery_prompt", None)
        if post_auth_redirect:
            flash(
                "Successfully reconnected to Kroger! Finishing your cart now.",
                "success",
            )
            return redirect(post_auth_redirect)
        flash("Successfully connected to Kroger!", "success")
    else:
        flash("Failed to connect to Kroger. Please try again.", "danger")

    session["open_modal"] = "modal-zipcode"
    return redirect(url_for("main.homepage"))


@kroger_bp.route("/location-search", methods=["POST"])
@require_login
def location_search() -> Response:
    """
    Send request to Kroger API for locations.

    Returns:
        Redirect to homepage with store selection modal
    """
    zipcode = request.form.get("zipcode")

    # Use household's Kroger user if set, otherwise current user
    kroger_user = _get_household_kroger_user()

    if not kroger_user or not kroger_user.oauth_token:
        flash("Please connect a Kroger account first", "danger")
        return redirect(url_for("main.homepage"))

    kroger_workflow = current_app.config.get("kroger_workflow")
    if not kroger_workflow:
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    redirect_url = kroger_workflow.handle_location_search(
        zipcode, kroger_user.oauth_token
    )
    return redirect(redirect_url)


@kroger_bp.route("/select-store", methods=["POST"])
@require_login
def select_store() -> Response:
    """
    Store user selected store ID in session.

    Returns:
        Redirect to homepage
    """
    store_id = request.form.get("store_id")

    kroger_workflow = current_app.config.get("kroger_workflow")
    if not kroger_workflow:
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    redirect_url = kroger_workflow.handle_store_selection(store_id)
    return redirect(redirect_url)


@kroger_bp.route("/product-search", methods=["GET", "POST"])
@require_login
def kroger_product_search() -> Response:
    """
    Search Kroger for ingredients based on name and present user with options.

    Returns:
        Redirect to homepage with product selection modal
    """
    # Get household's Kroger user
    kroger_user = _get_household_kroger_user()

    if not kroger_user or not kroger_user.oauth_token:
        flash("Please connect a Kroger account first", "danger")
        return redirect(url_for("main.homepage"))

    kroger_service = current_app.config.get("kroger_service")
    kroger_session_manager = current_app.config.get("kroger_session_manager")
    kroger_workflow = current_app.config.get("kroger_workflow")

    if not all([kroger_service, kroger_session_manager, kroger_workflow]):
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    # Handle custom search if provided
    if request.method == "POST":
        custom_search = request.form.get("custom_search", "").strip()
        if custom_search:
            # Perform custom search
            from kroger import parse_kroger_products

            response = kroger_service.search_products(
                custom_search, session.get("location_id"), kroger_user.oauth_token
            )
            if response:
                products = parse_kroger_products(response)
                # Get current ingredient detail or create a generic one
                current_ingredient = session.get(
                    "current_ingredient_detail",
                    {"name": custom_search, "quantity": "1", "measurement": "unit"},
                )
                kroger_session_manager.store_product_choices(
                    products, current_ingredient
                )
            return redirect(url_for("main.homepage") + "#modal-ingredient")

    # Default behavior - search for next ingredient
    redirect_url = kroger_workflow.handle_product_search(kroger_user.oauth_token)
    return redirect(redirect_url)


@kroger_bp.route("/item-choice", methods=["POST"])
@require_login
def item_choice() -> Response:
    """
    Store user selected product ID(s) and quantities in session.

    Returns:
        Redirect to product search or send to cart
    """
    # Support both single and multiple selections
    product_ids = request.form.getlist("product_id")
    quantities = request.form.getlist("quantity")

    if not product_ids:
        flash("Please select at least one product", "warning")
        return redirect(url_for("kroger.kroger_product_search"))

    kroger_session_manager = current_app.config.get("kroger_session_manager")
    if not kroger_session_manager:
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    # Ensure we have quantities for all products
    if len(quantities) < len(product_ids):
        quantities.extend(["1"] * (len(product_ids) - len(quantities)))

    # Convert quantities to integers
    quantities = [int(q) if q.isdigit() and int(q) > 0 else 1 for q in quantities]

    # Add products to cart
    if len(product_ids) == 1:
        kroger_session_manager.add_product_to_cart(product_ids[0], quantities[0])
    else:
        kroger_session_manager.add_multiple_products_to_cart(product_ids, quantities)

    # Check if there are more ingredients
    if kroger_session_manager.has_more_ingredients():
        return redirect(url_for("kroger.kroger_product_search"))
    else:
        return redirect(url_for("kroger.kroger_send_to_cart"))


@kroger_bp.route("/send-to-cart", methods=["POST", "GET"])
@require_login
def kroger_send_to_cart() -> Response:
    """
    Add selected products to user's Kroger cart.

    Returns:
        Redirect to homepage or skipped ingredients modal
    """
    # Get household's Kroger user
    kroger_user = _get_household_kroger_user()

    kroger_session_manager = current_app.config.get("kroger_session_manager")
    kroger_workflow = current_app.config.get("kroger_workflow")

    if not kroger_session_manager or not kroger_workflow:
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    should_remove_added = request.args.get("remove_added") == "true"
    selected_recipient_ids = [
        int(recipient_id)
        for recipient_id in request.args.getlist("email_recipient_ids")
        if recipient_id.isdigit()
    ]
    include_grocery_list = request.args.get("include_grocery_list") == "true"

    # Check if there are skipped ingredients
    skipped = kroger_session_manager.get_skipped_ingredients()

    # Always show the export summary before the final send.
    if not request.args.get("confirmed"):
        return redirect(url_for("main.homepage") + "#modal-skipped")

    if not kroger_user or not kroger_user.oauth_token:
        _queue_send_to_cart_reconnect_prompt(
            "Your Kroger connection needs to be updated before we can send this cart. "
            "Your selections are still saved."
        )
        return redirect(url_for("main.homepage"))

    valid_token = kroger_workflow.ensure_valid_token(kroger_user)
    if not valid_token:
        _queue_send_to_cart_reconnect_prompt(
            "Your Kroger connection expired before we could send your cart. "
            "Reconnect to continue, and we’ll keep your current selections ready."
        )
        return redirect(url_for("main.homepage"))

    success = kroger_workflow.handle_send_to_cart(valid_token)
    if success:
        grocery_list_items = _build_grocery_list_email_items()
        if should_remove_added:
            _remove_exported_items_from_grocery_list(
                kroger_session_manager.get_skipped_grocery_list_item_ids(), skipped
            )
        if selected_recipient_ids:
            try:
                _send_household_kroger_order_created_emails(
                    recipient_ids=selected_recipient_ids,
                    removed_exported_items=should_remove_added,
                    include_grocery_list=include_grocery_list,
                    grocery_list_items=grocery_list_items,
                    skipped_items=skipped,
                )
            except Exception as e:
                logger.error(
                    f"Failed to send Kroger household notification emails: {e}",
                    exc_info=True,
                )
        _clear_kroger_flow_session(kroger_session_manager)
        return redirect("https://www.kroger.com/cart")

    session.pop("kroger_post_auth_redirect", None)
    _store_kroger_recovery_prompt(
        "We couldn't send your cart to Kroger",
        "Your selections are still saved, so you can try again without starting over.",
        "Try Again",
        _build_send_to_cart_resume_url(),
    )
    return redirect(url_for("main.homepage"))


@kroger_bp.route("/skip-ingredient", methods=["POST"])
@require_login
def skip_ingredient() -> Response:
    """
    Skip current ingredient and move to next one.

    Returns:
        Redirect to product search or send to cart
    """
    kroger_session_manager = current_app.config.get("kroger_session_manager")
    if not kroger_session_manager:
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    # Track the skipped ingredient
    current_ingredient = session.get("current_ingredient_detail", {})
    if current_ingredient:
        ingredient_name = _build_ingredient_label(
            current_ingredient.get("name", "Unknown"),
            current_ingredient.get("quantity", ""),
            current_ingredient.get("measurement", ""),
        )
        kroger_session_manager.track_skipped_ingredient(
            ingredient_name, current_ingredient.get("grocery_list_item_id")
        )

    if kroger_session_manager.has_more_ingredients():
        return redirect(url_for("kroger.kroger_product_search"))
    else:
        return redirect(url_for("kroger.kroger_send_to_cart"))
