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
                current_time = get_est_now()
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

    return jsonify(
        {
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": text,
                },
                "card": {"type": "LinkAccount"},
                "shouldEndSession": True,
            },
        }
    )


@alexa_bp.route("/add-item", methods=["POST"])
@verify_alexa_request
def add_item():
    """Add an item to the grocery list Alexa should use for this user.

    Uses the user's configured default Alexa grocery list if set; otherwise,
    falls back to their most recently modified planning list, optionally
    creating a new personal planning list if none exist.
    """

    try:
        alexa_request = request.get_json() or {}

        # Get access token from session
        access_token = (
            alexa_request.get("session", {})
            .get("user", {})
            .get("accessToken")
        )
        if not access_token:
            return _link_account_response(
                "Please link your Auto-Cart account in the Alexa app to use this skill."
            )

        # Get user
        user = get_user_from_access_token(access_token)
        if not user:
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": (
                                "I could not find your Auto-Cart account. "
                                "Please re-link your account in the Alexa app."
                            ),
                        },
                        "shouldEndSession": True,
                    },
                }
            )

        # Get intent slots
        intent = alexa_request.get("request", {}).get("intent", {}) or {}
        slots = intent.get("slots", {}) or {}

        item_name = (slots.get("item", {}) or {}).get("value", "") or ""
        item_name = item_name.strip()

        quantity_raw = (slots.get("quantity", {}) or {}).get("value")
        measurement_slot = (slots.get("measurement", {}) or {}).get("value")

        if not item_name:
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": (
                                "I didn't catch what item you want to add. Please try again."
                            ),
                        },
                        "shouldEndSession": False,
                    },
                }
            )

        # Determine which grocery list Alexa should use for this user
        grocery_list = get_target_grocery_list_for_user(user, create_if_missing=True)
        if not grocery_list:
            # As a safety net, this should rarely happen because create_if_missing=True
            logger.error(
                "Failed to determine or create a grocery list for Alexa user %s",
                user.id,
            )
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": (
                                "Sorry, I could not determine which grocery list to use. "
                                "Please check your Alexa settings in Auto-Cart."
                            ),
                        },
                        "shouldEndSession": True,
                    },
                }
            ), 500

        # --- Build ingredient text like manual input ---
        quantity_text = None
        if quantity_raw is not None:
            quantity_text = str(quantity_raw).strip()

        measurement_clean = (measurement_slot or "").strip()
        ingredient_parts = []
        if quantity_text:
            ingredient_parts.append(quantity_text)
        if measurement_clean and measurement_clean.lower() != "unit":
            ingredient_parts.append(measurement_clean)
        ingredient_parts.append(item_name)
        ingredient_text = " ".join(ingredient_parts) if ingredient_parts else item_name

        # --- Parse ingredient(s) using same flow as add_manual_ingredient ---
        parsed_ingredients = Recipe.parse_ingredients(ingredient_text)
        if not parsed_ingredients:
            parsed_ingredients = parse_simple_ingredient(ingredient_text)

        if not parsed_ingredients:
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": (
                                "I couldn't understand that ingredient. "
                                "Please say it like '2 cups of milk' or just 'milk'."
                            ),
                        },
                        "shouldEndSession": False,
                    },
                }
            )

        # Collect all current ingredients from the grocery list
        all_ingredients = []
        for existing_ingredient in grocery_list.recipe_ingredients:
            if not existing_ingredient:
                continue
            all_ingredients.append(
                {
                    "quantity": existing_ingredient.quantity,
                    "measurement": existing_ingredient.measurement,
                    "ingredient_name": existing_ingredient.ingredient_name,
                }
            )

        # Add the new ingredient(s) to the list
        for ingredient_data in parsed_ingredients:
            all_ingredients.append(
                {
                    "quantity": ingredient_data["quantity"],
                    "measurement": ingredient_data["measurement"],
                    "ingredient_name": ingredient_data["ingredient_name"],
                }
            )

        logger.debug("All ingredients before consolidation (Alexa): %s", all_ingredients)

        # Use AI to intelligently consolidate all ingredients, same as manual input
        consolidated_ingredients = GroceryList.consolidate_ingredients_with_openai(
            all_ingredients
        )

        logger.debug(
            "Consolidated ingredients for Alexa update: %s", consolidated_ingredients
        )

        # Clear existing items from the grocery list
        for item in grocery_list.items:
            db.session.delete(item)
        db.session.flush()

        # Create new consolidated ingredients and grocery list items
        for ingredient_data in consolidated_ingredients:
            quantity_string = str(ingredient_data["quantity"])

            # Convert quantity to float using shared utility
            quantity = parse_quantity_string(quantity_string)
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
            db.session.flush()  # Get the ID

            grocery_list_item = GroceryListItem(
                grocery_list_id=grocery_list.id,
                recipe_ingredient_id=recipe_ingredient.id,
                added_by_user_id=user.id,
                completed=False,
            )
            db.session.add(grocery_list_item)

        # Update last modified metadata
        grocery_list.last_modified_by_user_id = user.id
        grocery_list.last_modified_at = get_est_now()

        db.session.commit()

        # Build a simple response; we don't need to read back full list
        if len(parsed_ingredients) == 1:
            spoken_name = (
                parsed_ingredients[0].get("ingredient_name") or item_name
            )
            response_text = (
                f"I've added {spoken_name} to your Auto-Cart grocery list."
            )
        else:
            response_text = "I've updated your Auto-Cart grocery list."

        return jsonify(
            {
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": response_text,
                    },
                    "shouldEndSession": True,
                },
            }
        )

    except Exception as e:  # pragma: no cover - defensive
        logger.error("Error adding item via Alexa: %s", e, exc_info=True)
        return jsonify(
            {
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Sorry, I had trouble adding that item. Please try again.",
                    },
                    "shouldEndSession": True,
                },
            }
        ), 500


@alexa_bp.route("/read-list", methods=["POST"])
@verify_alexa_request
def read_list():
    """Read items from the grocery list Alexa should use for this user."""

    try:
        alexa_request = request.get_json() or {}

        # Get access token from session
        access_token = (
            alexa_request.get("session", {})
            .get("user", {})
            .get("accessToken")
        )
        if not access_token:
            return _link_account_response(
                "Please link your Auto-Cart account in the Alexa app to use this skill."
            )

        # Get user
        user = get_user_from_access_token(access_token)
        if not user:
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": (
                                "I could not find your Auto-Cart account. "
                                "Please re-link your account in the Alexa app."
                            ),
                        },
                        "shouldEndSession": True,
                    },
                }
            )

        # Determine which grocery list Alexa should use for this user
        current_list = get_target_grocery_list_for_user(
            user,
            create_if_missing=False,
        )

        if not current_list:
            empty_text = (
                "Your grocery list is empty. You can add items by saying, "
                "Alexa, ask Auto-Cart to add milk."
            )
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": empty_text,
                        },
                        "shouldEndSession": True,
                    },
                }
            )

        # Get unchecked items
        unchecked_items = GroceryListItem.query.filter_by(
            grocery_list_id=current_list.id,
            completed=False,
        ).all()

        if not unchecked_items:
            empty_text = (
                "Your grocery list is empty. You can add items by saying, "
                "Alexa, ask Auto-Cart to add milk."
            )
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": empty_text,
                        },
                        "shouldEndSession": True,
                    },
                }
            )

        # Build list of items for speech
        item_names = []
        for list_item in unchecked_items:
            ingredient = list_item.recipe_ingredient
            if not ingredient:
                continue

            name = (ingredient.ingredient_name or "").strip()
            if not name:
                continue

            qty = ingredient.quantity
            meas = (ingredient.measurement or "").strip() if ingredient.measurement else ""

            if qty and meas and meas != "unit":
                item_text = f"{qty} {meas} of {name}"
            elif qty:
                item_text = f"{qty} {name}"
            else:
                item_text = name

            item_names.append(item_text)

        if not item_names:
            empty_text = (
                "Your grocery list is empty. You can add items by saying, "
                "Alexa, ask Auto-Cart to add milk."
            )
            return jsonify(
                {
                    "version": "1.0",
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": empty_text,
                        },
                        "shouldEndSession": True,
                    },
                }
            )

        # Create speech output
        if len(item_names) == 1:
            speech_text = f"You have 1 item on your list: {item_names[0]}."
        else:
            items_text = ", ".join(item_names[:-1]) + f", and {item_names[-1]}"
            speech_text = (
                f"You have {len(item_names)} items on your list: {items_text}."
            )

        return jsonify(
            {
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": speech_text,
                    },
                    "shouldEndSession": True,
                },
            }
        )

    except Exception as e:  # pragma: no cover - defensive
        logger.error("Error reading list via Alexa: %s", e, exc_info=True)
        return jsonify(
            {
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Sorry, I had trouble reading your list. Please try again.",
                    },
                    "shouldEndSession": True,
                },
            }
        ), 500
