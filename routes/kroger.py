"""
Kroger API integration routes blueprint.

Handles Kroger authentication, product search, and cart management.
"""

from flask import Blueprint, request, flash, redirect, url_for, g, session, current_app
from werkzeug.wrappers import Response

from extensions import db
from models import User
from utils import require_login
from logging_config import logger

kroger_bp = Blueprint("kroger", __name__)


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

        kroger_session_manager.clear_kroger_session_data()
        result = kroger_workflow.handle_authentication(
            g.user,
            current_app.config["OAUTH2_BASE_URL"],
            current_app.config["REDIRECT_URL"],
        )
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
        flash("Successfully connected to Kroger!", "success")
    else:
        flash("Failed to connect to Kroger. Please try again.", "danger")

    session["show_modal"] = True
    return redirect(url_for("main.homepage") + "#modal-zipcode")


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
    kroger_user = g.user
    if g.household and g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

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
    kroger_user = g.user
    if g.household and g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

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
    kroger_user = g.user
    if g.household and g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

    if not kroger_user or not kroger_user.oauth_token:
        flash("Please connect a Kroger account first", "danger")
        return redirect(url_for("main.homepage"))

    kroger_session_manager = current_app.config.get("kroger_session_manager")
    kroger_workflow = current_app.config.get("kroger_workflow")

    if not kroger_session_manager or not kroger_workflow:
        flash("Kroger integration not configured", "danger")
        return redirect(url_for("main.homepage"))

    # Check if there are skipped ingredients
    skipped = kroger_session_manager.get_skipped_ingredients()

    # If there are skipped ingredients and we haven't confirmed yet, show modal
    if skipped and not request.args.get("confirmed"):
        return redirect(url_for("main.homepage") + "#modal-skipped")

    # Clear skipped ingredients and proceed to cart
    kroger_session_manager.clear_skipped_ingredients()
    redirect_url = kroger_workflow.handle_send_to_cart(kroger_user.oauth_token)
    return redirect(redirect_url)


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
        ingredient_name = f"{current_ingredient.get('quantity', '')} {current_ingredient.get('measurement', '')} {current_ingredient.get('name', 'Unknown')}".strip()
        kroger_session_manager.track_skipped_ingredient(ingredient_name)

    if kroger_session_manager.has_more_ingredients():
        return redirect(url_for("kroger.kroger_product_search"))
    else:
        return redirect(url_for("kroger.kroger_send_to_cart"))
