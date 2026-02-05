import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, render_template, request, flash, redirect, session, g, url_for, jsonify
from flask_mail import Mail
from sqlalchemy.exc import IntegrityError
from flask_bcrypt import Bcrypt
from logging_config import logger

from models import db, connect_db, User, Recipe, GroceryList, RecipeIngredient, Household, HouseholdMember, MealPlanEntry, GroceryListItem
from forms import UserAddForm, AddRecipeForm, LoginForm, UpdatePasswordForm, UpdateEmailForm, UpdateUsernameForm
from app_config import config
from utils import (
    require_login, require_admin, do_login, do_logout, initialize_session_defaults,
    CURR_USER_KEY, CURR_GROCERY_LIST_KEY, parse_quantity_string
)
from kroger import KrogerAPIService, KrogerSessionManager, KrogerWorkflow
from recipe_scraper import scrape_recipe_data

def create_app(config_name=None):
    app = Flask(__name__)

    # Determine config
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')
    if config_name == 'production':
        config_name = 'production'

    app.config.from_object(config[config_name])

    # Initialize extensions
    from models import bcrypt
    bcrypt.init_app(app)
    mail = Mail(app)

    # Initialize database
    connect_db(app)
    with app.app_context():
        db.create_all()

    # Initialize Kroger services
    kroger_service = KrogerAPIService(
        app.config['CLIENT_ID'],
        app.config['CLIENT_SECRET']
    )
    kroger_session_manager = KrogerSessionManager()
    kroger_workflow = KrogerWorkflow(kroger_service)

    return app, bcrypt, mail, kroger_service, kroger_session_manager, kroger_workflow

# Create app instance
app, bcrypt, mail, kroger_service, kroger_session_manager, kroger_workflow = create_app()

# Update routes to use app.config instead of imported constants
@app.route('/authenticate')
@require_login
def kroger_authenticate():
    """Redirect user to Kroger API for authentication"""
    try:
        kroger_session_manager.clear_kroger_session_data()
        result = kroger_workflow.handle_authentication(
            g.user,
            app.config['OAUTH2_BASE_URL'],
            app.config['REDIRECT_URL']
        )
        return redirect(result)
    except Exception as e:
        flash('Authentication error. Please try again.', 'danger')
        return redirect(url_for('homepage'))


@app.route('/callback')
@require_login
def callback():
    """Receive bearer token and profile ID from Kroger API."""
    authorization_code = request.args.get('code')
    error = request.args.get('error')

    if error:
        flash(f'Kroger authorization failed: {error}', 'danger')
        return redirect(url_for('homepage'))

    if not authorization_code:
        flash('No authorization code received from Kroger', 'danger')
        return redirect(url_for('homepage'))

    success = kroger_workflow.handle_callback(authorization_code, g.user, app.config['REDIRECT_URL'])
    if success:
        db.session.commit()
        flash('Successfully connected to Kroger!', 'success')
    else:
        flash('Failed to connect to Kroger. Please try again.', 'danger')

    session['show_modal'] = True
    return redirect(url_for('homepage') + '#modal-zipcode')


@app.route('/location-search', methods=['POST'])
@require_login
def location_search():
    """Send request to Kroger API for locations"""
    zipcode = request.form.get('zipcode')

    # Use household's Kroger user if set, otherwise current user
    kroger_user = g.user
    if g.household and g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

    if not kroger_user.oauth_token:
        flash('Please connect a Kroger account first', 'danger')
        return redirect(url_for('homepage'))

    redirect_url = kroger_workflow.handle_location_search(zipcode, kroger_user.oauth_token)
    return redirect(redirect_url)


@app.route('/select-store', methods=['POST'])
@require_login
def select_store():
    """Store user selected store ID in session"""
    store_id = request.form.get('store_id')
    redirect_url = kroger_workflow.handle_store_selection(store_id)
    return redirect(redirect_url)


@app.route('/product-search', methods=['GET', 'POST'])
@require_login
def kroger_product_search():
    """Search Kroger for ingredients based on name and present user with options."""
    # Get household's Kroger user
    kroger_user = g.user
    if g.household and g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

    if not kroger_user.oauth_token:
        flash('Please connect a Kroger account first', 'danger')
        return redirect(url_for('homepage'))

    # Handle custom search if provided
    if request.method == 'POST':
        custom_search = request.form.get('custom_search', '').strip()
        if custom_search:
            # Perform custom search
            from kroger import parse_kroger_products
            response = kroger_service.search_products(
                custom_search,
                session.get('location_id'),
                kroger_user.oauth_token
            )
            if response:
                products = parse_kroger_products(response)
                # Get current ingredient detail or create a generic one
                current_ingredient = session.get('current_ingredient_detail', {
                    'name': custom_search,
                    'quantity': '1',
                    'measurement': 'unit'
                })
                kroger_session_manager.store_product_choices(products, current_ingredient)
            return redirect(url_for('homepage') + '#modal-ingredient')

    # Default behavior - search for next ingredient
    redirect_url = kroger_workflow.handle_product_search(kroger_user.oauth_token)
    return redirect(redirect_url)


@app.route('/item-choice', methods=['POST'])
@require_login
def item_choice():
    """Store user selected product ID(s) and quantities in session"""
    # Support both single and multiple selections
    product_ids = request.form.getlist('product_id')
    quantities = request.form.getlist('quantity')

    if not product_ids:
        flash('Please select at least one product', 'warning')
        return redirect(url_for('kroger_product_search'))

    # Ensure we have quantities for all products
    if len(quantities) < len(product_ids):
        quantities.extend(['1'] * (len(product_ids) - len(quantities)))

    # Convert quantities to integers
    quantities = [int(q) if q.isdigit() and int(q) > 0 else 1 for q in quantities]

    # Add products to cart
    if len(product_ids) == 1:
        kroger_session_manager.add_product_to_cart(product_ids[0], quantities[0])
    else:
        kroger_session_manager.add_multiple_products_to_cart(product_ids, quantities)

    # Check if there are more ingredients
    if kroger_session_manager.has_more_ingredients():
        return redirect(url_for('kroger_product_search'))
    else:
        return redirect(url_for('kroger_send_to_cart'))


@app.route('/send-to-cart', methods=['POST', 'GET'])
@require_login
def kroger_send_to_cart():
    """Add selected products to user's Kroger cart"""
    # Get household's Kroger user
    kroger_user = g.user
    if g.household and g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

    if not kroger_user.oauth_token:
        flash('Please connect a Kroger account first', 'danger')
        return redirect(url_for('homepage'))

    # Check if there are skipped ingredients
    skipped = kroger_session_manager.get_skipped_ingredients()

    # If there are skipped ingredients and we haven't confirmed yet, show modal
    if skipped and not request.args.get('confirmed'):
        return redirect(url_for('homepage') + '#modal-skipped')

    # Clear skipped ingredients and proceed to cart
    kroger_session_manager.clear_skipped_ingredients()
    redirect_url = kroger_workflow.handle_send_to_cart(kroger_user.oauth_token)
    return redirect(redirect_url)


@app.route('/skip-ingredient', methods=['POST'])
@require_login
def skip_ingredient():
    """Skip current ingredient and move to next one"""
    # Track the skipped ingredient
    current_ingredient = session.get('current_ingredient_detail', {})
    if current_ingredient:
        ingredient_name = f"{current_ingredient.get('quantity', '')} {current_ingredient.get('measurement', '')} {current_ingredient.get('name', 'Unknown')}".strip()
        kroger_session_manager.track_skipped_ingredient(ingredient_name)

    if kroger_session_manager.has_more_ingredients():
        return redirect(url_for('kroger_product_search'))
    else:
        return redirect(url_for('kroger_send_to_cart'))


# User management routes
@app.route('/')
def homepage():
    """Show homepage with recipes and grocery list - requires login"""
    # Redirect to login if not authenticated
    if not g.user:
        return redirect(url_for('login'))

    # If user has no household, redirect to household creation
    if not g.household:
        return redirect(url_for('create_household'))

    initialize_session_defaults()

    # Get household recipes (both personal and shared)
    recipes = Recipe.query.filter(
        (Recipe.household_id == g.household.id) |
        ((Recipe.user_id == g.user.id) & (Recipe.household_id.is_(None)))
    ).all()

    selected_recipe_ids = session.get('selected_recipe_ids', [])
    logger.debug(f"Selected recipe IDs: {selected_recipe_ids}")
    logger.debug(f"User recipe IDs: {[recipe.id for recipe in recipes]}")

    # Get household members for email selection
    household_members = HouseholdMember.query.filter_by(household_id=g.household.id).all()
    household_users = [m.user for m in household_members]

    # Get all household grocery lists
    all_grocery_lists = GroceryList.query.filter_by(household_id=g.household.id).order_by(GroceryList.last_modified_at.desc()).all()

    form = AddRecipeForm()
    return render_template('index.html', form=form, recipes=recipes, selected_recipe_ids=selected_recipe_ids, all_users=household_users, all_grocery_lists=all_grocery_lists)


@app.route('/register', methods=["GET", "POST"])
def register():
    """Handle user signup"""
    form = UserAddForm()

    if form.validate_on_submit():
        user = User.signup(
            username=form.username.data.strip().capitalize(),
            password=form.password.data,
            email=form.email.data.strip()
        )

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError as error:
            if "users_email_key" in str(error.orig):
                flash("Email already taken", 'danger')
            elif "users_username_key" in str(error.orig):
                flash("Username already taken", 'danger')
            else:
                flash("An error occurred. Please try again.", 'danger')
            return render_template('register.html', form=form)

        do_login(user)
        # Redirect to household setup page
        flash('Welcome! Please create or join a household to get started.', 'info')
        return redirect(url_for('household_setup'))
    else:
        return render_template('register.html', form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    """Handle user login."""
    form = LoginForm()

    if form.validate_on_submit():
        user = User.authenticate(form.username.data.strip().capitalize(),
                                 form.password.data)

        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", "success")
            return redirect(url_for('homepage'))

        flash("Invalid credentials.", 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    """Handle logout of user."""
    do_logout()
    flash('Successfully logged out', 'success')
    return redirect(url_for('login'))


@app.route('/profile')
@require_login
def user_view():
    """Show user profile page"""
    return render_template('profile.html')


@app.route('/update-email', methods=['GET', 'POST'])
@require_login
def update_email():
    """Update user email"""
    form = UpdateEmailForm()

    if form.validate_on_submit():
        if bcrypt.check_password_hash(g.user.password, form.password.data):
            try:
                g.user.email = form.email.data.strip()
                db.session.commit()
                flash('Email updated successfully!', 'success')
                return redirect(url_for('user_view'))
            except IntegrityError:
                db.session.rollback()
                flash('Email already taken', 'danger')
        else:
            flash('Incorrect password', 'danger')

    return render_template('update_email.html', form=form)


@app.route('/update-username', methods=['GET', 'POST'])
@require_login
def update_username():
    """Update user username"""
    form = UpdateUsernameForm()

    if form.validate_on_submit():
        if bcrypt.check_password_hash(g.user.password, form.password.data):
            try:
                old_username = g.user.username
                new_username = form.username.data.strip()

                g.user.username = new_username

                # Update household name if user owns a household with the default naming pattern
                owned_households = HouseholdMember.query.filter_by(
                    user_id=g.user.id,
                    role='owner'
                ).all()

                households_updated = []
                for membership in owned_households:
                    household = membership.household
                    # Check if household name follows the pattern "{username}'s Household" (case-insensitive)
                    if household.name.lower() == f"{old_username.lower()}'s household":
                        household.name = f"{new_username}'s Household"
                        households_updated.append(household.name)

                db.session.commit()

                # Expire all objects to ensure fresh data on next request
                db.session.expire_all()

                flash('Username updated successfully!', 'success')
                if households_updated:
                    flash(f'Household name updated to: {", ".join(households_updated)}', 'success')
                return redirect(url_for('user_view'))
            except IntegrityError:
                db.session.rollback()
                flash('Username already taken', 'danger')
        else:
            flash('Incorrect password', 'danger')

    return render_template('update_username.html', form=form)


@app.route('/update-password', methods=['GET', 'POST'])
@require_login
def update_password():
    """Update user password"""
    form = UpdatePasswordForm()

    if form.validate_on_submit():
        try:
            g.user.change_password(
                form.current_password.data,
                form.new_password.data,
                form.confirm.data
            )
            db.session.commit()
            flash('Password updated successfully!', 'success')
            return redirect(url_for('user_view'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('update_password.html', form=form)


@app.route('/delete-account', methods=['POST'])
@require_login
def delete_account():
    """Delete user account"""
    user = g.user
    do_logout()
    db.session.delete(user)
    db.session.commit()
    flash('Account deleted successfully', 'success')
    return redirect(url_for('login'))


# Recipe management routes
@app.route('/add-recipe', methods=['POST'])
@require_login
def add_recipe():
    """Add a new recipe"""
    form = AddRecipeForm()

    if form.validate_on_submit():
        name = form.name.data
        ingredients_text = form.ingredients_text.data
        url = form.url.data
        notes = form.notes.data
        user_id = g.user.id

        # All recipes are household recipes
        visibility = 'household'

        try:
            recipe = Recipe.create_recipe(
                ingredients_text,
                url,
                user_id,
                name,
                notes,
                household_id=g.household.id if g.household else None,
                visibility=visibility
            )
            db.session.add(recipe)
            db.session.commit()
            flash('Recipe created successfully!', 'success')
            return redirect(url_for('homepage'))
        except Exception as error:
            db.session.rollback()
            logger.error(f"Recipe creation error: {error}", exc_info=True)
            flash('Error Occurred. Please try again', 'danger')
            return redirect(url_for('homepage'))
    else:
        logger.warning(f"Form validation failed: {form.errors}")
        flash('Form validation failed. Please check your input.', 'danger')
    return redirect(url_for('homepage'))


@app.route('/recipe/<int:recipe_id>', methods=["GET", "POST"])
def view_recipe(recipe_id):
    """View/Edit a user submitted recipe"""
    recipe = Recipe.query.get_or_404(recipe_id)

    ingredients_text = "\n".join(
        f"{ingr.quantity} {ingr.measurement} {ingr.ingredient_name}"
        for ingr in recipe.recipe_ingredients
    )

    form = AddRecipeForm(obj=recipe, ingredients_text=ingredients_text)

    if form.validate_on_submit():
        recipe.name = form.name.data
        recipe.url = form.url.data
        recipe.notes = form.notes.data

        # Clear existing ingredients
        for ingredient in recipe.recipe_ingredients:
            db.session.delete(ingredient)

        # Add new ingredients using the same logic as create_recipe
        ingredients = form.ingredients_text.data.split("\n")
        for ingredient in ingredients:
            ingredient = ingredient.strip()
            if ingredient:
                recipe_ingredient = RecipeIngredient(
                    quantity=1.0,
                    measurement="unit",
                    ingredient_name=ingredient[:40],
                )
                recipe.recipe_ingredients.append(recipe_ingredient)

        try:
            db.session.commit()
            flash('Recipe updated successfully!', 'success')
            return redirect(url_for('homepage'))
        except Exception as error:
            db.session.rollback()
            logger.error(f"Recipe update error: {error}", exc_info=True)
            flash('Error occurred. Please try again', 'danger')

    return render_template('recipe.html', recipe=recipe, form=form)


@app.route('/extract-recipe-form', methods=['POST'])
@require_login
def extract_recipe_form():
    """Extract recipe data from URL using web scraping"""
    url = request.form.get('url')

    if not url:
        return jsonify({'success': False, 'error': 'URL is required for recipe extraction'}), 400

    recipe_data = scrape_recipe_data(url)

    if recipe_data.get('error'):
        return jsonify({'success': False, 'error': f"Could not extract recipe: {recipe_data['error']}"}), 400
    elif recipe_data.get('name') or recipe_data.get('ingredients'):
        # Clean ingredients with OpenAI before populating form
        raw_ingredients_text = '\n'.join(recipe_data.get('ingredients', []))
        cleaned_ingredients_text = Recipe.clean_ingredients_with_openai(raw_ingredients_text)

        extracted_data = {
            'name': recipe_data.get('name', ''),
            'ingredients_text': cleaned_ingredients_text,
            'notes': recipe_data.get('instructions', ''),
            'url': url
        }

        return jsonify({'success': True, 'data': extracted_data})
    else:
        return jsonify({'success': False, 'error': 'No recipe data found on this page. Please enter manually.'}), 400


# Grocery list management routes
@app.route('/update_grocery_list', methods=['POST'])
@require_login
def update_grocery_list():
    """Add selected recipes to current grocery list"""
    selected_recipe_ids = request.form.getlist('recipe_ids')
    session['selected_recipe_ids'] = selected_recipe_ids

    grocery_list = g.grocery_list

    # If no grocery list exists, create a default one
    if not grocery_list and g.household:
        grocery_list = GroceryList(
            household_id=g.household.id,
            user_id=g.user.id,
            created_by_user_id=g.user.id,
            name="Household Grocery List",
            status='planning'
        )
        db.session.add(grocery_list)
        db.session.commit()
        session[CURR_GROCERY_LIST_KEY] = grocery_list.id
        g.grocery_list = grocery_list

    GroceryList.update_grocery_list(selected_recipe_ids, grocery_list=grocery_list, user_id=g.user.id)
    return redirect(url_for('homepage'))


@app.route('/grocery-list/create', methods=['POST'])
@require_login
def create_grocery_list():
    """Create a new grocery list for the household"""
    if not g.household:
        flash('You must be in a household to create a grocery list', 'danger')
        return redirect(url_for('homepage'))

    list_name = request.form.get('list_name', '').strip()
    if not list_name:
        flash('Please enter a list name', 'danger')
        return redirect(url_for('homepage'))

    new_list = GroceryList(
        household_id=g.household.id,
        user_id=g.user.id,
        created_by_user_id=g.user.id,
        name=list_name,
        status='planning'
    )
    db.session.add(new_list)
    db.session.commit()

    # Switch to the new list
    session[CURR_GROCERY_LIST_KEY] = new_list.id

    flash(f'Grocery list "{list_name}" created successfully!', 'success')
    return redirect(url_for('homepage'))


@app.route('/grocery-list/switch/<int:list_id>', methods=['POST'])
@require_login
def switch_grocery_list(list_id):
    """Switch to a different grocery list"""
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id,
        household_id=g.household.id
    ).first()

    if not grocery_list:
        flash('Grocery list not found', 'danger')
        return redirect(url_for('homepage'))

    session[CURR_GROCERY_LIST_KEY] = list_id
    flash(f'Switched to "{grocery_list.name}"', 'success')
    return redirect(url_for('homepage'))


@app.route('/grocery-list/rename/<int:list_id>', methods=['POST'])
@require_login
def rename_grocery_list(list_id):
    """Rename a grocery list"""
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id,
        household_id=g.household.id
    ).first()

    if not grocery_list:
        flash('Grocery list not found', 'danger')
        return redirect(url_for('homepage'))

    new_name = request.form.get('list_name', '').strip()
    if not new_name:
        flash('Please enter a list name', 'danger')
        return redirect(url_for('homepage'))

    old_name = grocery_list.name
    grocery_list.name = new_name
    db.session.commit()

    flash(f'Renamed "{old_name}" to "{new_name}"', 'success')
    return redirect(url_for('homepage'))


@app.route('/grocery-list/delete/<int:list_id>', methods=['POST'])
@require_login
def delete_grocery_list(list_id):
    """Delete a grocery list"""
    # Verify the list belongs to the user's household
    grocery_list = GroceryList.query.filter_by(
        id=list_id,
        household_id=g.household.id
    ).first()

    if not grocery_list:
        flash('Grocery list not found', 'danger')
        return redirect(url_for('homepage'))

    # Don't allow deleting the last list
    all_lists = GroceryList.query.filter_by(household_id=g.household.id).all()
    if len(all_lists) <= 1:
        flash('Cannot delete the last grocery list', 'danger')
        return redirect(url_for('homepage'))

    list_name = grocery_list.name

    # If this is the active list, switch to another one
    if session.get(CURR_GROCERY_LIST_KEY) == list_id:
        other_list = GroceryList.query.filter(
            GroceryList.household_id == g.household.id,
            GroceryList.id != list_id
        ).first()
        if other_list:
            session[CURR_GROCERY_LIST_KEY] = other_list.id

    db.session.delete(grocery_list)
    db.session.commit()

    flash(f'Deleted "{list_name}"', 'success')
    return redirect(url_for('homepage'))


@app.route('/clear_grocery_list', methods=['POST'])
@require_login
def clear_grocery_list():
    """Clear all items from the current grocery list"""
    grocery_list = g.grocery_list

    if grocery_list:
        # Delete all grocery list items
        for item in grocery_list.items:
            db.session.delete(item)
        db.session.commit()
        flash('Grocery list cleared successfully!', 'success')
    else:
        flash('No grocery list found', 'error')

    # Clear selected recipe IDs from session
    session.pop('selected_recipe_ids', None)

    return redirect(url_for('homepage'))


def parse_simple_ingredient(ingredient_text):
    """Simple ingredient parser for basic ingredients without complex formatting."""
    import re

    ingredient_text = ingredient_text.strip()
    if not ingredient_text:
        return []

    # Try to match pattern: "number unit ingredient" (e.g., "2 cups flour")
    pattern = r'^(\d+(?:/\d+)?(?:\.\d+)?)\s+(\w+)\s+(.*)'
    match = re.match(pattern, ingredient_text)

    if match:
        quantity, measurement, ingredient_name = match.groups()
        return [{
            "quantity": quantity.strip(),
            "measurement": measurement.strip(),
            "ingredient_name": ingredient_name.strip()
        }]

    # Try to match pattern: "number ingredient" (e.g., "2 apples")
    pattern = r'^(\d+(?:/\d+)?(?:\.\d+)?)\s+(.*)'
    match = re.match(pattern, ingredient_text)

    if match:
        quantity, ingredient_name = match.groups()
        return [{
            "quantity": quantity.strip(),
            "measurement": "item",
            "ingredient_name": ingredient_name.strip()
        }]

    # Default: treat as single item without unit (e.g., "pickles")
    return [{
        "quantity": "",
        "measurement": "",
        "ingredient_name": ingredient_text
    }]


@app.route('/add_manual_ingredient', methods=['POST'])
@require_login
def add_manual_ingredient():
    """Add a manually entered ingredient to the grocery list"""
    ingredient_text = request.form.get('ingredient_text', '').strip()

    if not ingredient_text:
        flash('Please enter an ingredient', 'error')
        return redirect(url_for('homepage'))

    try:
        # Try to parse the ingredient using OpenAI first, then fallback to simple parsing
        parsed_ingredients = Recipe.parse_ingredients(ingredient_text)

        # If OpenAI parsing fails or returns empty, use simple manual parsing
        if not parsed_ingredients:
            # Simple manual parsing for basic ingredients
            parsed_ingredients = parse_simple_ingredient(ingredient_text)

        if not parsed_ingredients:
            flash('Could not parse ingredient. Please use format like "2 cups flour" or just "pickles"', 'error')
            return redirect(url_for('homepage'))

        grocery_list = g.grocery_list

        # If no grocery list exists, create a default one
        if not grocery_list and g.household:
            grocery_list = GroceryList(
                household_id=g.household.id,
                user_id=g.user.id,
                created_by_user_id=g.user.id,
                name="Household Grocery List",
                status='planning'
            )
            db.session.add(grocery_list)
            db.session.commit()
            session[CURR_GROCERY_LIST_KEY] = grocery_list.id
            g.grocery_list = grocery_list

        # Apply the same consolidation logic as update_grocery_list
        from collections import defaultdict

        # Get existing ingredients from grocery list
        existing_ingredients = defaultdict(lambda: [])
        for existing_ingredient in grocery_list.recipe_ingredients:
            ingredient_name = existing_ingredient.ingredient_name
            existing_ingredients[ingredient_name].append({
                'quantity': existing_ingredient.quantity,
                'measurement': existing_ingredient.measurement,
                'ingredient_obj': existing_ingredient
            })

        # Process new ingredients
        for ingredient_data in parsed_ingredients:
            quantity_string = ingredient_data["quantity"]
            ingredient_name = ingredient_data["ingredient_name"]
            measurement = ingredient_data["measurement"]

            # Convert quantity to float using shared utility
            quantity = parse_quantity_string(quantity_string)
            if quantity is None:
                flash(f'Invalid quantity for ingredient: {ingredient_data["ingredient_name"]}', 'error')
                continue

            # Check if we can combine with existing ingredient
            combined = False
            for existing_entry in existing_ingredients[ingredient_name]:
                if existing_entry["measurement"] == measurement:
                    # Only combine if both have quantities, otherwise treat as separate
                    if quantity > 0 and existing_entry["ingredient_obj"].quantity > 0:
                        existing_entry["ingredient_obj"].quantity += quantity
                        combined = True
                        break

            if not combined:
                # Create new ingredient
                from models import RecipeIngredient
                new_ingredient = RecipeIngredient(
                    ingredient_name=ingredient_name,
                    quantity=quantity,
                    measurement=measurement
                )
                grocery_list.recipe_ingredients.append(new_ingredient)

        db.session.commit()
        flash('Ingredient added successfully!', 'success')
        return redirect(url_for('homepage'))

    except Exception as e:
        db.session.rollback()
        flash('Error adding ingredient. Please try again.', 'error')
        return redirect(url_for('homepage'))


# Email functionality
@app.route('/email-modal', methods=['GET', 'POST'])
@require_login
def email_modal():
    """Show email modal"""
    session['show_modal'] = True
    return redirect(url_for('homepage'))


@app.route('/send-email', methods=['POST'])
@require_login
def send_grocery_list_email():
    """Send grocery list and selected recipes to user supplied email(s)"""
    # Get selected user emails and custom email
    selected_user_emails = request.form.getlist('user_emails')
    custom_email = request.form.get('custom_email', '').strip()

    # Combine all emails
    all_emails = list(selected_user_emails)
    if custom_email:
        all_emails.append(custom_email)

    if not all_emails:
        flash('Please select at least one recipient or enter an email address', 'danger')
        return redirect(url_for('homepage') + '#email-modal')

    email_type = request.form.get('email_type', 'list_and_recipes')
    selected_recipe_ids = request.form.getlist('recipe_ids')
    grocery_list = g.grocery_list

    try:
        # Send to all selected emails
        for email in all_emails:
            if email_type == 'recipes_only':
                # Send only recipes
                GroceryList.send_recipes_only_email(email, selected_recipe_ids, mail)
            else:
                # Send grocery list and recipes (current functionality)
                if grocery_list:
                    GroceryList.send_email(email, grocery_list, selected_recipe_ids, mail)
                else:
                    flash("No grocery list found", "error")
                    return redirect(url_for('homepage'))

        # Success message
        recipient_count = len(all_emails)
        if email_type == 'recipes_only':
            flash(f"Recipes sent successfully to {recipient_count} recipient(s)!", "success")
        else:
            flash(f"List sent successfully to {recipient_count} recipient(s)!", "success")
    except Exception as e:
        logger.error(f"Email error: {e}", exc_info=True)
        flash("Email service is currently unavailable. Please try again later.", "danger")

    return redirect(url_for('homepage'))


@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@require_login
def delete_recipe(recipe_id):
    """Delete a recipe"""
    recipe = Recipe.query.get_or_404(recipe_id)

    if recipe.user_id != g.user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('user_view'))

    db.session.delete(recipe)
    db.session.commit()
    flash('Recipe deleted successfully!', 'success')
    return redirect(url_for('user_view'))


@app.route('/standardize-ingredients', methods=['POST'])
@require_login
def standardize_ingredients():
    """Standardize ingredients using OpenAI"""
    ingredients_text = request.form.get('ingredients_text')

    if not ingredients_text:
        return jsonify({'success': False, 'error': 'Ingredients text is required'}), 400

    try:
        standardized_ingredients = Recipe.clean_ingredients_with_openai(ingredients_text)

        return jsonify({
            'success': True,
            'data': {
                'standardized_ingredients': standardized_ingredients
            }
        })
    except Exception as e:
        logger.error(f"Error standardizing ingredients: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to standardize ingredients. Please try again.'}), 500


@app.route('/test-kroger-credentials')
def test_kroger_credentials():
    """Test if Kroger credentials are working"""
    try:
        # Test a simple API call that doesn't require user auth
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {kroger_service._encode_client_credentials()}'
        }

        # Try to get a client credentials token (this tests if your app is registered correctly)
        response = requests.post(
            f"{OAUTH2_BASE_URL}/token",
            headers=headers,
            data='grant_type=client_credentials&scope=product.compact',
            timeout=10
        )

        if response.status_code == 200:
            return f"✅ Kroger credentials are valid! Response: {response.json()}"
        else:
            return f"❌ Kroger credentials failed. Status: {response.status_code}, Response: {response.text}"

    except Exception as e:
        return f"❌ Error testing credentials: {e}"


@app.route('/delete_ingredient', methods=['POST'])
@require_login
def delete_ingredient():
    """Delete a specific ingredient from the grocery list"""
    ingredient_id = request.form.get('ingredient_id')

    if not ingredient_id:
        return jsonify({'success': False, 'error': 'Invalid ingredient'}), 400

    from models import RecipeIngredient
    ingredient = RecipeIngredient.query.get(ingredient_id)

    if not ingredient:
        return jsonify({'success': False, 'error': 'Ingredient not found'}), 404

    # Check if ingredient belongs to user's grocery list
    if ingredient not in g.grocery_list.recipe_ingredients:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    try:
        g.grocery_list.recipe_ingredients.remove(ingredient)
        db.session.delete(ingredient)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ingredient removed successfully!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to remove ingredient'}), 500


@app.route('/update_ingredient', methods=['POST'])
@require_login
def update_ingredient():
    """Update a specific ingredient in the grocery list"""
    ingredient_id = request.form.get('ingredient_id')
    quantity = request.form.get('quantity')
    measurement = request.form.get('measurement', '').strip()
    name = request.form.get('name', '').strip()

    if not ingredient_id or not name:
        return jsonify({'success': False, 'error': 'Invalid ingredient data'}), 400

    from models import RecipeIngredient
    ingredient = RecipeIngredient.query.get(ingredient_id)

    if not ingredient:
        return jsonify({'success': False, 'error': 'Ingredient not found'}), 404

    # Check if ingredient belongs to user's grocery list
    if ingredient not in g.grocery_list.recipe_ingredients:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    try:
        # Update ingredient fields
        ingredient.ingredient_name = name
        ingredient.quantity = float(quantity) if quantity else None
        ingredient.measurement = measurement if measurement else None

        db.session.commit()
        return jsonify({'success': True, 'message': 'Ingredient updated successfully!'})
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid quantity value'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to update ingredient'}), 500


# Household management routes
@app.route('/household/setup', methods=['GET', 'POST'])
@require_login
def household_setup():
    """Setup page for new users to create or join a household"""
    # If user already has a household, redirect to homepage
    if g.household:
        return redirect(url_for('homepage'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create':
            household_name = request.form.get('household_name', '').strip()

            if not household_name:
                flash('Please enter a household name', 'danger')
                return render_template('household_setup.html')

            # Create household
            household = Household(name=household_name)
            db.session.add(household)
            db.session.flush()

            # Add user as owner
            membership = HouseholdMember(
                household_id=household.id,
                user_id=g.user.id,
                role='owner'
            )
            db.session.add(membership)

            # Create default grocery list
            default_list = GroceryList(
                household_id=household.id,
                user_id=g.user.id,
                created_by_user_id=g.user.id,
                name="Household Grocery List",
                status='planning'
            )
            db.session.add(default_list)
            db.session.commit()

            # Set as active household
            session['household_id'] = household.id
            session[CURR_GROCERY_LIST_KEY] = default_list.id

            flash(f'Household "{household_name}" created successfully!', 'success')
            return redirect(url_for('homepage'))

        elif action == 'join':
            join_code = request.form.get('join_code', '').strip()

            if not join_code:
                flash('Please enter a household code or username', 'danger')
                return render_template('household_setup.html')

            # Try to find household by owner username
            owner = User.query.filter_by(username=join_code).first()
            if owner:
                # Find household where this user is owner
                membership = HouseholdMember.query.filter_by(
                    user_id=owner.id,
                    role='owner'
                ).first()

                if membership:
                    # Check if user is already a member
                    existing_membership = HouseholdMember.query.filter_by(
                        household_id=membership.household_id,
                        user_id=g.user.id
                    ).first()

                    if existing_membership:
                        flash(f'You are already a member of {membership.household.name}', 'warning')
                        session['household_id'] = membership.household_id
                        return redirect(url_for('homepage'))

                    # Add current user to this household
                    try:
                        new_membership = HouseholdMember(
                            household_id=membership.household_id,
                            user_id=g.user.id,
                            role='member'
                        )
                        db.session.add(new_membership)
                        db.session.commit()

                        session['household_id'] = membership.household_id
                        flash(f'Successfully joined {membership.household.name}!', 'success')
                        return redirect(url_for('homepage'))
                    except IntegrityError:
                        db.session.rollback()
                        flash('Error joining household. You may already be a member.', 'danger')
                        return render_template('household_setup.html')

            flash('Household not found. Please check the username and try again.', 'danger')
            return render_template('household_setup.html')

    return render_template('household_setup.html')


@app.route('/household/create', methods=['GET', 'POST'])
@require_login
def create_household():
    """Create a new household"""
    if request.method == 'POST':
        household_name = request.form.get('household_name', '').strip()

        if not household_name:
            flash('Please enter a household name', 'danger')
            return render_template('create_household.html')

        # Create household
        household = Household(name=household_name)
        db.session.add(household)
        db.session.flush()

        # Add user as owner
        membership = HouseholdMember(
            household_id=household.id,
            user_id=g.user.id,
            role='owner'
        )
        db.session.add(membership)

        # Create default grocery list for the household
        default_list = GroceryList(
            household_id=household.id,
            user_id=g.user.id,
            created_by_user_id=g.user.id,
            name="Household Grocery List",
            status='planning'
        )
        db.session.add(default_list)
        db.session.commit()

        # Set as active household
        session['household_id'] = household.id
        session[CURR_GROCERY_LIST_KEY] = default_list.id

        flash(f'Household "{household_name}" created successfully!', 'success')
        return redirect(url_for('homepage'))

    return render_template('create_household.html')


@app.route('/household/switch/<int:household_id>')
@require_login
def switch_household(household_id):
    """Switch to a different household"""
    # Verify user is a member
    membership = HouseholdMember.query.filter_by(
        household_id=household_id,
        user_id=g.user.id
    ).first()

    if not membership:
        flash('You are not a member of that household', 'danger')
        return redirect(url_for('homepage'))

    session['household_id'] = household_id
    flash('Switched household successfully', 'success')
    return redirect(url_for('homepage'))


@app.route('/household/settings')
@require_login
def household_settings():
    """View and manage household settings"""
    if not g.household:
        return redirect(url_for('create_household'))

    members = HouseholdMember.query.filter_by(household_id=g.household.id).all()

    # Get Kroger account user if set
    kroger_user = None
    if g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

    return render_template('household_settings.html',
                         household=g.household,
                         members=members,
                         kroger_user=kroger_user,
                         is_owner=(g.household_member.role == 'owner'))


@app.route('/household/invite', methods=['POST'])
@require_login
def invite_household_member():
    """Invite a user to the household by username"""
    if not g.household or g.household_member.role != 'owner':
        flash('Only household owners can invite members', 'danger')
        return redirect(url_for('household_settings'))

    username = request.form.get('username', '').strip()

    if not username:
        flash('Please enter a username', 'danger')
        return redirect(url_for('household_settings'))

    # Find user
    user = User.query.filter_by(username=username).first()
    if not user:
        flash(f'User "{username}" not found', 'danger')
        return redirect(url_for('household_settings'))

    # Check if already a member
    existing = HouseholdMember.query.filter_by(
        household_id=g.household.id,
        user_id=user.id
    ).first()

    if existing:
        flash(f'{username} is already a member of this household', 'warning')
        return redirect(url_for('household_settings'))

    # Add as member
    membership = HouseholdMember(
        household_id=g.household.id,
        user_id=user.id,
        role='member'
    )
    db.session.add(membership)
    db.session.commit()

    flash(f'{username} added to household successfully!', 'success')
    return redirect(url_for('household_settings'))


@app.route('/household/remove-member/<int:user_id>', methods=['POST'])
@require_login
def remove_household_member(user_id):
    """Remove a member from the household"""
    if not g.household or g.household_member.role != 'owner':
        flash('Only household owners can remove members', 'danger')
        return redirect(url_for('household_settings'))

    if user_id == g.user.id:
        flash('You cannot remove yourself from the household', 'danger')
        return redirect(url_for('household_settings'))

    membership = HouseholdMember.query.filter_by(
        household_id=g.household.id,
        user_id=user_id
    ).first()

    if not membership:
        flash('Member not found', 'danger')
        return redirect(url_for('household_settings'))

    db.session.delete(membership)
    db.session.commit()

    flash('Member removed successfully', 'success')
    return redirect(url_for('household_settings'))


@app.route('/household/set-kroger-user/<int:user_id>', methods=['POST'])
@require_login
def set_kroger_user(user_id):
    """Set the household's Kroger account user"""
    if not g.household or g.household_member.role != 'owner':
        flash('Only household owners can set the Kroger account', 'danger')
        return redirect(url_for('household_settings'))

    # Verify user is a member and has Kroger connected
    membership = HouseholdMember.query.filter_by(
        household_id=g.household.id,
        user_id=user_id
    ).first()

    if not membership:
        flash('User is not a member of this household', 'danger')
        return redirect(url_for('household_settings'))

    user = User.query.get(user_id)
    if not user.oauth_token:
        flash('This user has not connected their Kroger account yet', 'warning')
        return redirect(url_for('household_settings'))

    g.household.kroger_user_id = user_id
    db.session.commit()

    flash(f'Kroger account set to {user.username}', 'success')
    return redirect(url_for('household_settings'))


@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""
    # Skip database queries for migration endpoint to avoid schema errors
    if request.endpoint == 'migrate_database':
        g.user = None
        return

    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])

        # Update last activity timestamp
        if g.user and request.endpoint not in ['static', None]:
            from datetime import datetime
            g.user.last_activity = datetime.utcnow()
            db.session.commit()
    else:
        g.user = None

@app.before_request
def add_household_to_g():
    """Add current household to Flask global."""
    # Skip for migration endpoint
    if request.endpoint == 'migrate_database':
        g.household = None
        g.household_member = None
        return

    g.household = None
    g.household_member = None

    if g.user:
        # Get household from session or use the first one
        household_id = session.get('household_id')

        if household_id:
            # Verify user is a member of this household
            membership = HouseholdMember.query.filter_by(
                household_id=household_id,
                user_id=g.user.id
            ).first()

            if membership:
                g.household = Household.query.get(household_id)
                g.household_member = membership

        # If no household in session or invalid, get user's first household
        if not g.household:
            membership = HouseholdMember.query.filter_by(user_id=g.user.id).first()
            if membership:
                g.household = membership.household
                g.household_member = membership
                session['household_id'] = g.household.id

@app.before_request
def add_grocery_list_to_g():
    """Add current grocery list to Flask global."""
    # Skip for migration endpoint
    if request.endpoint == 'migrate_database':
        g.grocery_list = None
        return

    g.grocery_list = None

    if g.user and g.household:
        # Try to get the grocery list from session first
        list_id = session.get(CURR_GROCERY_LIST_KEY)
        grocery_list = None

        if list_id:
            # Verify the list exists and belongs to the household
            grocery_list = GroceryList.query.filter_by(
                id=list_id,
                household_id=g.household.id
            ).first()

        # If no valid list in session, get the most recently modified planning list
        if not grocery_list:
            grocery_list = GroceryList.query.filter_by(
                household_id=g.household.id,
                status='planning'
            ).order_by(GroceryList.last_modified_at.desc()).first()

        # If still no list, create a default one
        if not grocery_list:
            grocery_list = GroceryList(
                household_id=g.household.id,
                user_id=g.user.id,
                created_by_user_id=g.user.id,
                name="Household Grocery List"
            )
            db.session.add(grocery_list)
            db.session.commit()

        g.grocery_list = grocery_list
        session[CURR_GROCERY_LIST_KEY] = grocery_list.id


# Meal planning routes
@app.route('/meal-plan')
@require_login
def meal_plan():
    """Show weekly meal plan for household"""
    if not g.household:
        flash('Please create or join a household first', 'warning')
        return redirect(url_for('homepage'))

    from datetime import datetime, timedelta

    # Get week offset from query params (0 = this week, 1 = next week, etc.)
    week_offset = int(request.args.get('week', 0))

    # Calculate start of week (Monday)
    today = datetime.now().date()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    # Get meal plan entries for this week
    meal_entries = MealPlanEntry.query.filter(
        MealPlanEntry.household_id == g.household.id,
        MealPlanEntry.date >= week_start,
        MealPlanEntry.date <= week_end
    ).all()

    # Organize entries by date and meal type
    meal_plan = {}
    for i in range(7):
        day = week_start + timedelta(days=i)
        meal_plan[day] = {
            'breakfast': [],
            'lunch': [],
            'dinner': []
        }

    for entry in meal_entries:
        if entry.date in meal_plan and entry.meal_type in meal_plan[entry.date]:
            meal_plan[entry.date][entry.meal_type].append(entry)

    # Get all household recipes for the dropdown
    recipes = Recipe.query.filter_by(household_id=g.household.id).all()

    # Get household members for cook assignment
    household_members = HouseholdMember.query.filter_by(household_id=g.household.id).all()
    household_users = [m.user for m in household_members]

    return render_template(
        'meal_plan.html',
        meal_plan=meal_plan,
        week_start=week_start,
        week_end=week_end,
        week_offset=week_offset,
        today=today,
        recipes=recipes,
        household_users=household_users
    )


@app.route('/meal-plan/add', methods=['POST'])
@require_login
def add_meal_plan_entry():
    """Add a recipe to the meal plan"""
    if not g.household:
        flash('Please create or join a household first', 'warning')
        return redirect(url_for('homepage'))

    from datetime import datetime

    recipe_id = request.form.get('recipe_id')
    custom_meal_name = request.form.get('custom_meal_name', '').strip()
    date_str = request.form.get('date')
    meal_type = request.form.get('meal_type')
    assigned_cook_id = request.form.get('assigned_cook_id')
    notes = request.form.get('notes', '').strip()

    # Convert empty string to None for assigned_cook_id
    if assigned_cook_id == '':
        assigned_cook_id = None
    elif assigned_cook_id:
        assigned_cook_id = int(assigned_cook_id)

    # Must have either recipe_id or custom_meal_name
    if (not recipe_id or recipe_id == 'custom') and not custom_meal_name:
        flash('Please select a recipe or enter a custom meal name', 'danger')
        return redirect(url_for('meal_plan'))

    if not date_str or not meal_type:
        flash('Missing required fields', 'danger')
        return redirect(url_for('meal_plan'))

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Determine if this is a custom meal or recipe
        if recipe_id == 'custom' or not recipe_id:
            entry = MealPlanEntry(
                household_id=g.household.id,
                recipe_id=None,
                custom_meal_name=custom_meal_name,
                date=date,
                meal_type=meal_type,
                assigned_cook_user_id=assigned_cook_id,
                notes=notes if notes else None
            )
        else:
            entry = MealPlanEntry(
                household_id=g.household.id,
                recipe_id=int(recipe_id),
                custom_meal_name=None,
                date=date,
                meal_type=meal_type,
                assigned_cook_user_id=assigned_cook_id,
                notes=notes if notes else None
            )

        db.session.add(entry)
        db.session.commit()

        flash('Meal added to plan!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding meal plan entry: {e}", exc_info=True)
        flash('Error adding meal to plan', 'danger')

    return redirect(url_for('meal_plan') + f'?week={request.form.get("week_offset", 0)}')


@app.route('/meal-plan/delete/<int:entry_id>', methods=['POST'])
@require_login
def delete_meal_plan_entry(entry_id):
    """Delete a meal plan entry"""
    entry = MealPlanEntry.query.get_or_404(entry_id)

    if entry.household_id != g.household.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('meal_plan'))

    week_offset = request.form.get('week_offset', 0)

    db.session.delete(entry)
    db.session.commit()

    flash('Meal removed from plan', 'success')
    return redirect(url_for('meal_plan') + f'?week={week_offset}')


@app.route('/meal-plan/add-to-list', methods=['POST'])
@require_login
def add_meal_plan_to_list():
    """Add recipes from meal plan to grocery list"""
    if not g.household:
        flash('Please create or join a household first', 'warning')
        return redirect(url_for('homepage'))

    from datetime import datetime, timedelta

    # Get week offset
    week_offset = int(request.form.get('week_offset', 0))

    # Calculate week range
    today = datetime.now().date()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    # Get all meal plan entries for this week
    meal_entries = MealPlanEntry.query.filter(
        MealPlanEntry.household_id == g.household.id,
        MealPlanEntry.date >= week_start,
        MealPlanEntry.date <= week_end
    ).all()

    if not meal_entries:
        flash('No meals planned for this week', 'warning')
        return redirect(url_for('meal_plan') + f'?week={week_offset}')

    # Get unique recipe IDs
    recipe_ids = list(set([str(entry.recipe_id) for entry in meal_entries]))

    # Add to current grocery list
    grocery_list = g.grocery_list

    # If no grocery list exists, create one
    if not grocery_list and g.household:
        grocery_list = GroceryList(
            household_id=g.household.id,
            user_id=g.user.id,
            created_by_user_id=g.user.id,
            name="Household Grocery List",
            status='planning'
        )
        db.session.add(grocery_list)
        db.session.commit()
        session[CURR_GROCERY_LIST_KEY] = grocery_list.id
        g.grocery_list = grocery_list

    GroceryList.update_grocery_list(recipe_ids, grocery_list=grocery_list, user_id=g.user.id)

    flash(f'Added {len(meal_entries)} meals to grocery list!', 'success')
    return redirect(url_for('homepage'))


# Shopping mode routes
@app.route('/shopping-mode')
@require_login
def shopping_mode():
    """Streamlined shopping interface"""
    if not g.grocery_list:
        flash('Please select a grocery list first', 'warning')
        return redirect(url_for('homepage'))

    grocery_list = g.grocery_list

    # Get all items with their ingredients
    items = GroceryListItem.query.filter_by(grocery_list_id=grocery_list.id).all()

    # Calculate progress
    total_items = len(items)
    checked_items = sum(1 for item in items if item.is_checked)

    return render_template(
        'shopping_mode.html',
        grocery_list=grocery_list,
        items=items,
        total_items=total_items,
        checked_items=checked_items
    )


@app.route('/shopping-mode/start', methods=['POST'])
@require_login
def start_shopping():
    """Start a shopping session"""
    if not g.grocery_list:
        flash('Please select a grocery list first', 'warning')
        return redirect(url_for('homepage'))

    grocery_list = g.grocery_list
    grocery_list.status = 'shopping'
    grocery_list.shopping_user_id = g.user.id
    grocery_list.last_modified_by_user_id = g.user.id

    db.session.commit()

    flash('Shopping session started!', 'success')
    return redirect(url_for('shopping_mode'))


@app.route('/shopping-mode/end', methods=['POST'])
@require_login
def end_shopping():
    """End a shopping session and remove checked items"""
    if not g.grocery_list:
        flash('Please select a grocery list first', 'warning')
        return redirect(url_for('homepage'))

    grocery_list = g.grocery_list

    # Delete all checked items
    checked_items = GroceryListItem.query.filter_by(
        grocery_list_id=grocery_list.id,
        completed=True
    ).all()

    num_removed = len(checked_items)
    for item in checked_items:
        db.session.delete(item)

    grocery_list.status = 'done'
    grocery_list.shopping_user_id = None
    grocery_list.last_modified_by_user_id = g.user.id

    db.session.commit()

    if num_removed > 0:
        flash(f'Shopping session completed! {num_removed} checked item(s) removed.', 'success')
    else:
        flash('Shopping session completed!', 'success')
    return redirect(url_for('homepage'))


@app.route('/shopping-mode/toggle/<int:item_id>', methods=['POST'])
@require_login
def toggle_item(item_id):
    """Toggle item checked status"""
    item = GroceryListItem.query.get_or_404(item_id)

    if item.grocery_list_id != g.grocery_list.id:
        return jsonify({'error': 'Unauthorized'}), 403

    item.is_checked = not item.is_checked

    # Update last modified
    grocery_list = g.grocery_list
    grocery_list.last_modified_by_user_id = g.user.id

    db.session.commit()

    return jsonify({
        'success': True,
        'is_checked': item.is_checked,
        'item_id': item.id
    })


# API endpoints for polling
@app.route('/api/grocery-list/<int:list_id>/state')
@require_login
def grocery_list_state(list_id):
    """Get current state of grocery list for polling"""
    grocery_list = GroceryList.query.get_or_404(list_id)

    # Check authorization
    if grocery_list.household_id != g.household.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Get item count
    item_count = GroceryListItem.query.filter_by(grocery_list_id=list_id).count()
    checked_count = GroceryListItem.query.filter_by(grocery_list_id=list_id, is_checked=True).count()

    return jsonify({
        'status': grocery_list.status,
        'last_modified_at': grocery_list.last_modified_at.isoformat() if grocery_list.last_modified_at else None,
        'last_modified_by': grocery_list.last_modified_by.username if grocery_list.last_modified_by else None,
        'shopping_user': grocery_list.shopping_user.username if grocery_list.shopping_user else None,
        'item_count': item_count,
        'checked_count': checked_count
    })


# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            if user.is_admin:
                do_login(user)
                flash('Admin login successful!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Access denied. Admin privileges required.', 'danger')
        else:
            flash('Invalid username or password', 'danger')

    return render_template('admin_login.html')


@app.route('/admin/dashboard')
@require_admin
def admin_dashboard():
    """Admin dashboard showing all users"""
    users = User.query.order_by(User.last_activity.desc().nullslast()).all()
    return render_template('admin_dashboard.html', users=users)


@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@require_admin
def admin_delete_user(user_id):
    """Delete a user from the admin panel"""
    if user_id == g.user.id:
        flash('You cannot delete your own admin account', 'danger')
        return redirect(url_for('admin_dashboard'))

    user = User.query.get_or_404(user_id)
    username = user.username

    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'User "{username}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {e}", exc_info=True)
        flash('Error deleting user. Please try again.', 'danger')

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/migrate-database', methods=['GET', 'POST'])
def migrate_database():
    """One-time migration to fix database schema issues - NO AUTH REQUIRED for emergency fixes"""
    if request.method == 'GET':
        return render_template('admin_migrate.html')

    from sqlalchemy import text

    logger.info("Starting database migrations...")
    migration_results = []

    # Migration 1: Add is_admin column to users table if it doesn't exist
    try:
        logger.info("Checking for is_admin column...")
        db.session.execute(text("SELECT is_admin FROM users LIMIT 1"))
        db.session.commit()
        migration_results.append("✓ is_admin column already exists")
    except Exception as e:
        db.session.rollback()  # Rollback the failed transaction
        logger.info(f"is_admin column check failed: {e}")
        try:
            logger.info("Adding is_admin column to users table...")
            db.session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            migration_results.append("✓ Added is_admin column to users table")
            logger.info("is_admin column added successfully")
        except Exception as e2:
            db.session.rollback()
            migration_results.append(f"❌ Failed to add is_admin: {str(e2)[:100]}")
            logger.error(f"Failed to add is_admin column: {e2}")

    # Migration 1b: Add last_activity column to users table if it doesn't exist
    try:
        logger.info("Checking for last_activity column...")
        db.session.execute(text("SELECT last_activity FROM users LIMIT 1"))
        db.session.commit()
        migration_results.append("✓ last_activity column already exists")
    except Exception as e:
        db.session.rollback()  # Rollback the failed transaction
        logger.info(f"last_activity column check failed: {e}")
        try:
            logger.info("Adding last_activity column to users table...")
            db.session.execute(text("ALTER TABLE users ADD COLUMN last_activity TIMESTAMP"))
            db.session.commit()
            migration_results.append("✓ Added last_activity column to users table")
            logger.info("last_activity column added successfully")
        except Exception as e2:
            db.session.rollback()
            migration_results.append(f"❌ Failed to add last_activity: {str(e2)[:100]}")
            logger.error(f"Failed to add last_activity column: {e2}")

    # Migration 2: Add multiple missing columns to grocery_lists table
    grocery_list_columns = [
        ("household_id", "INTEGER REFERENCES households(id) ON DELETE CASCADE"),
        ("name", "TEXT NOT NULL DEFAULT 'My Grocery List'"),
        ("status", "VARCHAR(20) NOT NULL DEFAULT 'planning'"),
        ("store", "TEXT"),
        ("created_by_user_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL"),
        ("created_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("last_modified_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("last_modified_by_user_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL"),
        ("shopping_user_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL"),
    ]

    for col_name, col_type in grocery_list_columns:
        try:
            logger.info(f"Checking for {col_name} column in grocery_lists...")
            db.session.execute(text(f"SELECT {col_name} FROM grocery_lists LIMIT 1"))
            db.session.commit()
            migration_results.append(f"✓ {col_name} column already exists in grocery_lists")
        except Exception as e:
            db.session.rollback()
            logger.info(f"{col_name} column check failed: {e}")
            try:
                logger.info(f"Adding {col_name} column to grocery_lists table...")
                db.session.execute(text(f"ALTER TABLE grocery_lists ADD COLUMN {col_name} {col_type}"))
                db.session.commit()
                migration_results.append(f"✓ Added {col_name} column to grocery_lists table")
                logger.info(f"{col_name} column added successfully")
            except Exception as e2:
                db.session.rollback()
                migration_results.append(f"❌ Failed to add {col_name}: {str(e2)[:100]}")
                logger.error(f"Failed to add {col_name} column: {e2}")

    # Migration 3: Add missing columns to recipes table
    recipes_columns = [
        ("household_id", "INTEGER REFERENCES households(id) ON DELETE CASCADE"),
        ("visibility", "VARCHAR(20) NOT NULL DEFAULT 'private'"),
        ("created_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ]

    for col_name, col_type in recipes_columns:
        try:
            logger.info(f"Checking for {col_name} column in recipes...")
            db.session.execute(text(f"SELECT {col_name} FROM recipes LIMIT 1"))
            db.session.commit()
            migration_results.append(f"✓ {col_name} column already exists in recipes")
        except Exception as e:
            db.session.rollback()
            logger.info(f"{col_name} column check failed: {e}")
            try:
                logger.info(f"Adding {col_name} column to recipes table...")
                db.session.execute(text(f"ALTER TABLE recipes ADD COLUMN {col_name} {col_type}"))
                db.session.commit()
                migration_results.append(f"✓ Added {col_name} column to recipes table")
                logger.info(f"{col_name} column added successfully")
            except Exception as e2:
                db.session.rollback()
                migration_results.append(f"❌ Failed to add {col_name}: {str(e2)[:100]}")
                logger.error(f"Failed to add {col_name} column: {e2}")

    # Migration 4: Add custom_meal_name column to meal_plan_entries if it doesn't exist
    try:
        logger.info("Checking for custom_meal_name column...")
        db.session.execute(text("SELECT custom_meal_name FROM meal_plan_entries LIMIT 1"))
        db.session.commit()
        migration_results.append("✓ custom_meal_name column already exists")
    except Exception as e:
        db.session.rollback()  # Rollback the failed transaction
        logger.info(f"custom_meal_name column check failed: {e}")
        try:
            logger.info("Adding custom_meal_name column to meal_plan_entries table...")
            db.session.execute(text("ALTER TABLE meal_plan_entries ADD COLUMN custom_meal_name VARCHAR(200)"))
            db.session.commit()
            migration_results.append("✓ Added custom_meal_name column to meal_plan_entries table")
            logger.info("custom_meal_name column added successfully")
        except Exception as e2:
            db.session.rollback()
            migration_results.append(f"❌ Failed to add custom_meal_name: {str(e2)[:100]}")
            logger.error(f"Failed to add custom_meal_name column: {e2}")

    # Migration 5: Make recipe_id nullable in meal_plan_entries (PostgreSQL version)
    try:
        logger.info("Making recipe_id nullable in meal_plan_entries...")
        db.session.execute(text("ALTER TABLE meal_plan_entries ALTER COLUMN recipe_id DROP NOT NULL"))
        db.session.commit()
        migration_results.append("✓ Made recipe_id nullable in meal_plan_entries table")
        logger.info("recipe_id is now nullable")
    except Exception as e:
        db.session.rollback()
        # If it's already nullable or the command fails, that's okay
        migration_results.append(f"⚠ recipe_id nullable: {str(e)[:100]}")
        logger.info(f"recipe_id nullable check: {e}")

    logger.info("All migrations completed!")

    flash('✅ Database migrations completed! Results: ' + ' | '.join(migration_results), 'success')
    return redirect(url_for('homepage'))


@app.route('/admin/setup-admin', methods=['GET', 'POST'])
def setup_admin():
    """One-time setup to make a user an admin - NO AUTH REQUIRED for initial setup"""
    if request.method == 'GET':
        return render_template('admin_setup.html')

    try:
        email = request.form.get('email')

        if not email:
            flash('❌ Email is required', 'danger')
            return redirect(url_for('setup_admin'))

        logger.info(f"Looking for user with email: {email}")
        user = User.query.filter_by(email=email).first()

        if not user:
            flash(f'❌ No user found with email: {email}', 'danger')
            return redirect(url_for('setup_admin'))

        # Make the user an admin
        user.is_admin = True
        db.session.commit()

        logger.info(f"User {user.username} ({user.email}) is now an admin!")
        flash(f'✅ User {user.username} ({user.email}) is now an admin!', 'success')
        return redirect(url_for('homepage'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin setup error: {e}", exc_info=True)
        flash(f'❌ Admin setup failed: {str(e)}', 'danger')
        return redirect(url_for('setup_admin'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
