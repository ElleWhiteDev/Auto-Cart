"""Alexa Skill API endpoints for Auto-Cart.

This module exposes endpoints that the Alexa skill calls to:
- Add items to a grocery list
- Read the current grocery list

Requests are authenticated via an access token that is stored on the User
model as ``alexa_access_token`` and configured from the profile screen.

The target grocery list is chosen per-user based on their configured
Alexa default list or their most recent planning list across households.
"""

from datetime import datetime
from typing import Optional
from functools import wraps

from flask import Blueprint, request, jsonify, current_app

from models import db, User, GroceryList, Recipe, RecipeIngredient, GroceryListItem
from utils import get_est_now, parse_quantity_string, parse_simple_ingredient
from logging_config import logger


alexa_bp = Blueprint("alexa", __name__, url_prefix="/api/alexa")

ALEXA_EMPTY_LIST_TEXT = (
    "Your grocery list is empty. You can add items by saying, "
    "Alexa, ask Auto-Cart to add milk."
)
ALEXA_ADD_ITEM_REPROMPT = "Try saying add bananas."
ALEXA_WELCOME_TEXT = (
    "Welcome to Auto-Cart. You can say add bananas, or ask me to read your "
    "grocery list."
)
ALEXA_HELP_TEXT = (
    "You can ask me to add an item, like say add bananas, or ask what is on "
    "my grocery list."
)
ALEXA_FALLBACK_TEXT = (
    "I can add items and read your grocery list. Try saying add bananas."
)


def verify_alexa_request(f):
    """Basic verification that a request came from Alexa.

    This performs lightweight checks that are sufficient for development:

    * Ensures the request timestamp is within 150 seconds of ``get_est_now()``
    * Optionally verifies the Alexa application ID if ``ALEXA_SKILL_ID`` is set

    Full certificate-chain verification is required for production but is
    intentionally omitted here for simplicity.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            alexa_request = request.get_json() or {}

            # Verify timestamp freshness (within 150 seconds)
            timestamp_str = alexa_request.get("request", {}).get("timestamp")
            if timestamp_str:
                request_time = datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00")
                )
                current_time = (
                    datetime.now(request_time.tzinfo)
                    if request_time.tzinfo
                    else get_est_now()
                )
                time_diff = abs((current_time - request_time).total_seconds())
                if time_diff > 150:
                    logger.warning(
                        "Alexa request timestamp too old: %s seconds", time_diff
                    )
                    return jsonify({"error": "Request timestamp too old"}), 400

            # Verify application ID (if configured)
            expected_app_id = current_app.config.get("ALEXA_SKILL_ID")
            app_id = (
                alexa_request.get("session", {})
                .get("application", {})
                .get("applicationId")
            )
            if expected_app_id and app_id != expected_app_id:
                logger.warning("Invalid Alexa application ID: %s", app_id)
                return jsonify({"error": "Invalid application ID"}), 403

        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error verifying Alexa request: %s", exc, exc_info=True)
            return jsonify({"error": "Invalid request format"}), 400

        return f(*args, **kwargs)

    return decorated_function


def get_user_from_access_token(access_token: Optional[str]) -> Optional[User]:
    """Look up a :class:`User` from the stored Alexa access token."""

    if not access_token:
        return None

    return User.query.filter_by(alexa_access_token=access_token).first()


def user_can_access_grocery_list(user: User, grocery_list: GroceryList) -> bool:
    """Return True if ``user`` can access ``grocery_list``.

    Rules:
    - If the list is household-scoped, the user must be a member of that
      household.
    - If it's a personal list (no household), the user must own it.
    """

    if not user or not grocery_list:
        return False

    # Household-scoped list: check user's memberships
    if grocery_list.household_id:
        for membership in user.household_memberships:
            if membership.household_id == grocery_list.household_id:
                return True
        return False

    # Personal list: must be owned by the user
    return grocery_list.user_id == user.id


def get_target_grocery_list_for_user(
    user: User,
    create_if_missing: bool = False,
) -> Optional[GroceryList]:
    """Determine which grocery list Alexa should use for this user.

    Priority:

    1. User's configured ``alexa_default_grocery_list`` (if still accessible)
    2. Most recently modified ``planning`` list from any household the user
    belongs to
    3. Most recently modified personal ``planning`` list (no household)
    4. Optionally create a new personal ``planning`` list if none exist
    """

    selected_list: Optional[GroceryList] = None

    # 1. Explicit default list configured on the user
    if getattr(user, "alexa_default_grocery_list_id", None):
        default_list = GroceryList.query.get(user.alexa_default_grocery_list_id)
        if default_list and user_can_access_grocery_list(user, default_list):
            selected_list = default_list
        else:
            logger.warning(
                "User %s has alexa_default_grocery_list_id=%s but cannot access that list; falling back.",
                user.id,
                user.alexa_default_grocery_list_id,
            )

    if not selected_list:
        # 2. Most recent planning list from any of the user's households
        household_ids = [
            m.household_id for m in user.household_memberships if m.household_id
        ]
        household_list: Optional[GroceryList] = None
        if household_ids:
            household_list = (
                GroceryList.query.filter(
                    GroceryList.household_id.in_(household_ids),
                    GroceryList.status == "planning",
                )
                .order_by(GroceryList.last_modified_at.desc())
                .first()
            )

        # 3. Most recent personal planning list (no household)
        personal_list: Optional[GroceryList] = (
            GroceryList.query.filter_by(
                user_id=user.id,
                household_id=None,
                status="planning",
            )
            .order_by(GroceryList.last_modified_at.desc())
            .first()
        )

        # Choose the newer of the household or personal planning lists
        if household_list and personal_list:
            if household_list.last_modified_at >= personal_list.last_modified_at:
                selected_list = household_list
            else:
                selected_list = personal_list
        elif household_list:
            selected_list = household_list
        elif personal_list:
            selected_list = personal_list

    # 4. Optionally create a new personal planning list if none exist
    if not selected_list and create_if_missing:
        selected_list = GroceryList(
            user_id=user.id,
            name="My Grocery List",
            status="planning",
            created_by_user_id=user.id,
            last_modified_by_user_id=user.id,
        )
        db.session.add(selected_list)
        db.session.flush()
        logger.info("Created new personal grocery list for Alexa user %s", user.id)

    return selected_list


def _link_account_response(text: str):
    """Helper to return a standard Alexa LinkAccount card response."""

    return _speech_response(text, card={"type": "LinkAccount"})


def _speech_response(
    text: str,
    should_end_session: bool = True,
    card: Optional[dict] = None,
    reprompt_text: Optional[str] = None,
):
    """Build a standard Alexa plain-text response payload."""

    response = {
        "outputSpeech": {
            "type": "PlainText",
            "text": text,
        },
        "shouldEndSession": should_end_session,
    }
    if card:
        response["card"] = card
    if reprompt_text:
        response["reprompt"] = {
            "outputSpeech": {
                "type": "PlainText",
                "text": reprompt_text,
            }
        }

    return jsonify({"version": "1.0", "response": response})


def _account_not_found_response():
    """Return a response for requests with an invalid Alexa access token."""

    return _speech_response(
        "I could not find your Auto-Cart account. Please re-link your account in the Alexa app."
    )


def _get_alexa_user(alexa_request):
    """Resolve the linked user from the Alexa request or return an Alexa response."""

    access_token = alexa_request.get("session", {}).get("user", {}).get("accessToken")
    if not access_token:
        return None, _link_account_response(
            "Please link your Auto-Cart account in the Alexa app to use this skill."
        )

    user = get_user_from_access_token(access_token)
    if not user:
        return None, _account_not_found_response()

    return user, None


def _build_ingredient_text(
    item_name: str,
    quantity_raw: Optional[str],
    measurement_slot: Optional[str],
) -> str:
    """Build an ingredient string matching the manual ingredient flow."""

    ingredient_parts = []
    quantity_text = str(quantity_raw).strip() if quantity_raw is not None else ""
    measurement_clean = (measurement_slot or "").strip()

    if quantity_text:
        ingredient_parts.append(quantity_text)
    if measurement_clean and measurement_clean.lower() != "unit":
        ingredient_parts.append(measurement_clean)
    ingredient_parts.append(item_name)
    return " ".join(ingredient_parts)


def _parse_alexa_ingredients(ingredient_text: str):
    """Parse Alexa ingredient text using the shared manual-input flow."""

    parsed_ingredients = Recipe.parse_ingredients(ingredient_text)
    if parsed_ingredients:
        return parsed_ingredients
    return parse_simple_ingredient(ingredient_text)


def _as_ingredient_payload(ingredient):
    """Convert an ingredient-like object to the consolidation payload shape."""

    return {
        "quantity": ingredient.quantity,
        "measurement": ingredient.measurement,
        "ingredient_name": ingredient.ingredient_name,
    }


def _get_all_ingredients_for_consolidation(
    grocery_list: GroceryList, parsed_ingredients
):
    """Collect existing and new ingredients for consolidation."""

    all_ingredients = [
        _as_ingredient_payload(existing_ingredient)
        for existing_ingredient in grocery_list.recipe_ingredients
        if existing_ingredient
    ]
    all_ingredients.extend(parsed_ingredients)
    return all_ingredients


def _replace_grocery_list_items(
    grocery_list: GroceryList,
    user: User,
    consolidated_ingredients,
):
    """Replace list items with newly consolidated ingredients."""

    for item in grocery_list.items:
        db.session.delete(item)
    db.session.flush()

    for ingredient_data in consolidated_ingredients:
        quantity = parse_quantity_string(str(ingredient_data["quantity"]))
        if quantity is None:
            logger.warning(
                "Skipping ingredient with invalid quantity in Alexa flow: %s",
                ingredient_data["ingredient_name"],
            )
            continue

        recipe_ingredient = RecipeIngredient(
            ingredient_name=ingredient_data["ingredient_name"],
            quantity=quantity,
            measurement=ingredient_data["measurement"],
        )
        db.session.add(recipe_ingredient)
        db.session.flush()

        grocery_list_item = GroceryListItem(
            grocery_list_id=grocery_list.id,
            recipe_ingredient_id=recipe_ingredient.id,
            added_by_user_id=user.id,
            completed=False,
        )
        db.session.add(grocery_list_item)

    grocery_list.last_modified_by_user_id = user.id
    grocery_list.last_modified_at = get_est_now()
    db.session.commit()


def _empty_list_response():
    """Return the standard Alexa empty grocery list response."""

    return _speech_response(ALEXA_EMPTY_LIST_TEXT)


def _format_list_item_for_speech(list_item: GroceryListItem) -> Optional[str]:
    """Return a speech-friendly phrase for a grocery list item."""

    ingredient = list_item.recipe_ingredient
    if not ingredient:
        return None

    name = (ingredient.ingredient_name or "").strip()
    if not name:
        return None

    qty = ingredient.quantity
    meas = (ingredient.measurement or "").strip() if ingredient.measurement else ""

    if qty and meas and meas != "unit":
        return f"{qty} {meas} of {name}"
    if qty:
        return f"{qty} {name}"
    return name


def _get_spoken_item_names(unchecked_items):
    """Build speech-ready item names from list items."""

    item_names = []
    for list_item in unchecked_items:
        spoken_item = _format_list_item_for_speech(list_item)
        if spoken_item:
            item_names.append(spoken_item)
    return item_names


def _handle_add_item_request(alexa_request):
    """Add an item to the user's target grocery list from an Alexa request."""

    try:
        user, error_response = _get_alexa_user(alexa_request)
        if error_response:
            return error_response

        intent = alexa_request.get("request", {}).get("intent", {}) or {}
        slots = intent.get("slots", {}) or {}

        item_name = (slots.get("item", {}) or {}).get("value", "") or ""
        item_name = item_name.strip()

        quantity_raw = (slots.get("quantity", {}) or {}).get("value")
        measurement_slot = (slots.get("measurement", {}) or {}).get("value")

        if not item_name:
            return _speech_response(
                "I didn't catch what item you want to add. Please try again.",
                should_end_session=False,
            )

        grocery_list = get_target_grocery_list_for_user(user, create_if_missing=True)
        if not grocery_list:
            logger.error(
                "Failed to determine or create a grocery list for Alexa user %s",
                user.id,
            )
            return (
                _speech_response(
                    "Sorry, I could not determine which grocery list to use. Please check your Alexa settings in Auto-Cart."
                ),
                500,
            )

        ingredient_text = _build_ingredient_text(
            item_name,
            quantity_raw,
            measurement_slot,
        )
        parsed_ingredients = _parse_alexa_ingredients(ingredient_text)

        if not parsed_ingredients:
            return _speech_response(
                "I couldn't understand that ingredient. Please say it like '2 cups of milk' or just 'milk'.",
                should_end_session=False,
            )

        all_ingredients = _get_all_ingredients_for_consolidation(
            grocery_list,
            parsed_ingredients,
        )

        logger.debug(
            "All ingredients before consolidation (Alexa): %s", all_ingredients
        )

        consolidated_ingredients = GroceryList.consolidate_ingredients_with_openai(
            all_ingredients
        )

        logger.debug(
            "Consolidated ingredients for Alexa update: %s", consolidated_ingredients
        )

        _replace_grocery_list_items(
            grocery_list,
            user,
            consolidated_ingredients,
        )

        if len(parsed_ingredients) == 1:
            spoken_name = parsed_ingredients[0].get("ingredient_name") or item_name
            response_text = f"I've added {spoken_name} to your Auto-Cart grocery list."
        else:
            response_text = "I've updated your Auto-Cart grocery list."

        return _speech_response(response_text)

    except Exception as e:  # pragma: no cover - defensive
        logger.error("Error adding item via Alexa: %s", e, exc_info=True)
        return (
            _speech_response(
                "Sorry, I had trouble adding that item. Please try again."
            ),
            500,
        )


def _handle_read_list_request(alexa_request):
    """Read grocery list items aloud from an Alexa request."""

    try:
        user, error_response = _get_alexa_user(alexa_request)
        if error_response:
            return error_response

        current_list = get_target_grocery_list_for_user(
            user,
            create_if_missing=False,
        )

        if not current_list:
            return _empty_list_response()

        unchecked_items = GroceryListItem.query.filter_by(
            grocery_list_id=current_list.id,
            completed=False,
        ).all()

        if not unchecked_items:
            return _empty_list_response()

        item_names = _get_spoken_item_names(unchecked_items)

        if not item_names:
            return _empty_list_response()

        if len(item_names) == 1:
            speech_text = f"You have 1 item on your list: {item_names[0]}."
        else:
            items_text = ", ".join(item_names[:-1]) + f", and {item_names[-1]}"
            speech_text = (
                f"You have {len(item_names)} items on your list: {items_text}."
            )

        return _speech_response(speech_text)

    except Exception as e:  # pragma: no cover - defensive
        logger.error("Error reading list via Alexa: %s", e, exc_info=True)
        return (
            _speech_response(
                "Sorry, I had trouble reading your list. Please try again."
            ),
            500,
        )


@alexa_bp.route("/webhook", methods=["POST"])
@verify_alexa_request
def alexa_webhook():
    """Primary Alexa custom-skill webhook for launch and intent dispatch."""

    alexa_request = request.get_json() or {}
    request_type = alexa_request.get("request", {}).get("type")

    if request_type == "LaunchRequest":
        return _speech_response(
            ALEXA_WELCOME_TEXT,
            should_end_session=False,
            reprompt_text=ALEXA_ADD_ITEM_REPROMPT,
        )

    if request_type == "IntentRequest":
        intent_name = (
            alexa_request.get("request", {}).get("intent", {}).get("name") or ""
        )
        if intent_name == "AddItemIntent":
            return _handle_add_item_request(alexa_request)
        if intent_name == "ReadListIntent":
            return _handle_read_list_request(alexa_request)
        if intent_name == "AMAZON.HelpIntent":
            return _speech_response(
                ALEXA_HELP_TEXT,
                should_end_session=False,
                reprompt_text=ALEXA_ADD_ITEM_REPROMPT,
            )
        if intent_name in {"AMAZON.CancelIntent", "AMAZON.StopIntent"}:
            return _speech_response("Okay, goodbye.")

        return _speech_response(
            ALEXA_FALLBACK_TEXT,
            should_end_session=False,
            reprompt_text=ALEXA_ADD_ITEM_REPROMPT,
        )

    if request_type == "SessionEndedRequest":
        return jsonify({"version": "1.0", "response": {}})

    return _speech_response(
        "Sorry, I couldn't handle that Alexa request.",
        should_end_session=True,
    )


@alexa_bp.route("/add-item", methods=["POST"])
@verify_alexa_request
def add_item():
    """Add an item to the grocery list Alexa should use for this user.

    Uses the user's configured default Alexa grocery list if set; otherwise,
    falls back to their most recently modified planning list, optionally
    creating a new personal planning list if none exist.
    """

    alexa_request = request.get_json() or {}
    return _handle_add_item_request(alexa_request)


@alexa_bp.route("/read-list", methods=["POST"])
@verify_alexa_request
def read_list():
    """Read items from the grocery list Alexa should use for this user."""

    alexa_request = request.get_json() or {}
    return _handle_read_list_request(alexa_request)
