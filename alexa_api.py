"""
Alexa Skill API endpoints for Auto-Cart

This module provides REST API endpoints that Amazon Alexa can call to:
- Add items to the current grocery list
- Read the current grocery list
- Authenticate users via OAuth 2.0
"""

import os
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from functools import wraps
from models import db, User, GroceryList, RecipeIngredient, GroceryListItem
from utils import get_est_now
from logging_config import logger

alexa_bp = Blueprint('alexa', __name__, url_prefix='/api/alexa')


def verify_alexa_request(f):
    """
    Decorator to verify that requests are actually coming from Amazon Alexa.

    Amazon requires verification of:
    1. Signature certificate chain
    2. Request timestamp (within 150 seconds)
    3. Application ID matches your skill

    For now, we'll implement basic checks. Full implementation would include
    certificate chain validation.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the request data
        try:
            alexa_request = request.get_json()

            # Verify timestamp (must be within 150 seconds)
            timestamp_str = alexa_request.get('request', {}).get('timestamp')
            if timestamp_str:
                request_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                current_time = get_est_now()
                time_diff = abs((current_time - request_time).total_seconds())

                if time_diff > 150:
                    logger.warning(f"Alexa request timestamp too old: {time_diff} seconds")
                    return jsonify({'error': 'Request timestamp too old'}), 400

            # TODO: Verify signature certificate chain
            # This requires downloading and validating Amazon's signing certificate
            # For MVP, we'll skip this but it's required for production

            # Verify application ID (if configured)
            app_id = alexa_request.get('session', {}).get('application', {}).get('applicationId')
            expected_app_id = current_app.config.get('ALEXA_SKILL_ID')

            if expected_app_id and app_id != expected_app_id:
                logger.warning(f"Invalid Alexa application ID: {app_id}")
                return jsonify({'error': 'Invalid application ID'}), 403

        except Exception as e:
            logger.error(f"Error verifying Alexa request: {e}", exc_info=True)
            return jsonify({'error': 'Invalid request format'}), 400

        return f(*args, **kwargs)
    return decorated_function


def get_user_from_access_token(access_token):
    """
    Get user from OAuth access token.
    For now, we'll use a simple token stored in the user table.
    In production, this would validate a proper OAuth token.
    """
    if not access_token:
        return None

    # Look up user by their alexa_access_token
    user = User.query.filter_by(alexa_access_token=access_token).first()
    return user


@alexa_bp.route('/add-item', methods=['POST'])
@verify_alexa_request
def add_item():
    """
    Add an item to the user's current grocery list.

    Expected Alexa request format:
    {
        "session": {
            "user": {
                "accessToken": "user-oauth-token"
            }
        },
        "request": {
            "type": "IntentRequest",
            "intent": {
                "name": "AddItemIntent",
                "slots": {
                    "item": {"value": "milk"},
                    "quantity": {"value": "2"},
                    "measurement": {"value": "gallons"}
                }
            }
        }
    }
    """
    try:
        alexa_request = request.get_json()

        # Get access token from session
        access_token = alexa_request.get('session', {}).get('user', {}).get('accessToken')
        if not access_token:
            return jsonify({
                'version': '1.0',
                'response': {
                    'outputSpeech': {
                        'type': 'PlainText',
                        'text': 'Please link your Auto-Cart account in the Alexa app to use this skill.'
                    },
                    'card': {
                        'type': 'LinkAccount'
                    },
                    'shouldEndSession': True
                }
            })

        # Get user
        user = get_user_from_access_token(access_token)
        if not user:
            return jsonify({
                'version': '1.0',
                'response': {
                    'outputSpeech': {
                        'type': 'PlainText',
                        'text': 'I could not find your Auto-Cart account. Please re-link your account in the Alexa app.'
                    },
                    'shouldEndSession': True
                }
            })

        # Get intent slots
        intent = alexa_request.get('request', {}).get('intent', {})
        slots = intent.get('slots', {})

        item_name = slots.get('item', {}).get('value', '').strip()
        quantity = slots.get('quantity', {}).get('value', '1')
        measurement = slots.get('measurement', {}).get('value', 'unit')

        if not item_name:
            return jsonify({
                'version': '1.0',
                'response': {
                    'outputSpeech': {
                        'type': 'PlainText',
                        'text': 'I didn\'t catch what item you want to add. Please try again.'
                    },
                    'shouldEndSession': False
                }
            })

        # Get user's current grocery list
        current_list = GroceryList.query.filter_by(
            user_id=user.id,
            status='planning'
        ).order_by(GroceryList.last_modified_at.desc()).first()

        if not current_list:
            # Create a new list if none exists
            current_list = GroceryList(
                user_id=user.id,
                household_id=None,  # Personal list
                name="My Grocery List",
                status="planning"
            )
            db.session.add(current_list)
            db.session.flush()

        # Create a RecipeIngredient for this item
        # (even though it's not from a recipe, we use this for consistency)
        ingredient = RecipeIngredient(
            recipe_id=None,  # Not from a recipe
            name=item_name,
            quantity=quantity,
            measurement=measurement
        )
        db.session.add(ingredient)
        db.session.flush()

        # Add to grocery list
        list_item = GroceryListItem(
            grocery_list_id=current_list.id,
            recipe_ingredient_id=ingredient.id,
            checked=False
        )
        db.session.add(list_item)
        db.session.commit()

        # Build response
        quantity_text = f"{quantity} {measurement}" if measurement != 'unit' else quantity
        response_text = f"I've added {quantity_text} of {item_name} to your Auto-Cart grocery list."

        return jsonify({
            'version': '1.0',
            'response': {
                'outputSpeech': {
                    'type': 'PlainText',
                    'text': response_text
                },
                'shouldEndSession': True
            }
        })

    except Exception as e:
        logger.error(f"Error adding item via Alexa: {e}", exc_info=True)
        return jsonify({
            'version': '1.0',
            'response': {
                'outputSpeech': {
                    'type': 'PlainText',
                    'text': 'Sorry, I had trouble adding that item. Please try again.'
                },
                'shouldEndSession': True
            }
        }), 500


@alexa_bp.route('/read-list', methods=['POST'])
@verify_alexa_request
def read_list():
    """
    Read items from the user's current grocery list.

    Expected Alexa request format:
    {
        "session": {
            "user": {
                "accessToken": "user-oauth-token"
            }
        },
        "request": {
            "type": "IntentRequest",
            "intent": {
                "name": "ReadListIntent"
            }
        }
    }
    """
    try:
        alexa_request = request.get_json()

        # Get access token from session
        access_token = alexa_request.get('session', {}).get('user', {}).get('accessToken')
        if not access_token:
            return jsonify({
                'version': '1.0',
                'response': {
                    'outputSpeech': {
                        'type': 'PlainText',
                        'text': 'Please link your Auto-Cart account in the Alexa app to use this skill.'
                    },
                    'card': {
                        'type': 'LinkAccount'
                    },
                    'shouldEndSession': True
                }
            })

        # Get user
        user = get_user_from_access_token(access_token)
        if not user:
            return jsonify({
                'version': '1.0',
                'response': {
                    'outputSpeech': {
                        'type': 'PlainText',
                        'text': 'I could not find your Auto-Cart account. Please re-link your account in the Alexa app.'
                    },
                    'shouldEndSession': True
                }
            })

        # Get user's current grocery list
        current_list = GroceryList.query.filter_by(
            user_id=user.id,
            status='planning'
        ).order_by(GroceryList.last_modified_at.desc()).first()

        if not current_list:
            return jsonify({
                'version': '1.0',
                'response': {
                    'outputSpeech': {
                        'type': 'PlainText',
                        'text': 'Your grocery list is empty. You can add items by saying, Alexa, ask Auto-Cart to add milk.'
                    },
                    'shouldEndSession': True
                }
            })

        # Get unchecked items
        unchecked_items = GroceryListItem.query.filter_by(
            grocery_list_id=current_list.id,
            checked=False
        ).all()

        if not unchecked_items:
            return jsonify({
                'version': '1.0',
                'response': {
                    'outputSpeech': {
                        'type': 'PlainText',
                        'text': 'Your grocery list is empty. You can add items by saying, Alexa, ask Auto-Cart to add milk.'
                    },
                    'shouldEndSession': True
                }
            })

        # Build list of items for speech
        item_names = []
        for list_item in unchecked_items:
            ingredient = list_item.recipe_ingredient
            if ingredient:
                # Format: "2 cups of milk" or just "milk"
                if ingredient.quantity and ingredient.measurement and ingredient.measurement != 'unit':
                    item_text = f"{ingredient.quantity} {ingredient.measurement} of {ingredient.name}"
                else:
                    item_text = ingredient.name
                item_names.append(item_text)

        # Create speech output
        if len(item_names) == 1:
            speech_text = f"You have 1 item on your list: {item_names[0]}."
        else:
            items_text = ", ".join(item_names[:-1]) + f", and {item_names[-1]}"
            speech_text = f"You have {len(item_names)} items on your list: {items_text}."

        return jsonify({
            'version': '1.0',
            'response': {
                'outputSpeech': {
                    'type': 'PlainText',
                    'text': speech_text
                },
                'shouldEndSession': True
            }
        })

    except Exception as e:
        logger.error(f"Error reading list via Alexa: {e}", exc_info=True)
        return jsonify({
            'version': '1.0',
            'response': {
                'outputSpeech': {
                    'type': 'PlainText',
                    'text': 'Sorry, I had trouble reading your list. Please try again.'
                },
                'shouldEndSession': True
            }
        }), 500
