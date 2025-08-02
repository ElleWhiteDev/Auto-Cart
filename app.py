import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, render_template, request, flash, redirect, session, g, url_for, jsonify
from flask_mail import Mail
from sqlalchemy.exc import IntegrityError
from flask_bcrypt import Bcrypt

from models import db, connect_db, User, Recipe, GroceryList
from forms import UserAddForm, AddRecipeForm, LoginForm, UpdatePasswordForm, UpdateEmailForm
from app_config import config
from utils import (
    require_login, do_login, do_logout, initialize_session_defaults,
    CURR_USER_KEY, CURR_GROCERY_LIST_KEY
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
    redirect_url = kroger_workflow.handle_location_search(zipcode, g.user.oath_token)
    return redirect(redirect_url)


@app.route('/select-store', methods=['POST'])
@require_login
def select_store():
    """Store user selected store ID in session"""
    store_id = request.form.get('store_id')
    redirect_url = kroger_workflow.handle_store_selection(store_id)
    return redirect(redirect_url)


@app.route('/product-search')
@require_login
def kroger_product_search():
    """Search Kroger for ingredients based on name and present user with options."""
    redirect_url = kroger_workflow.handle_product_search(g.user.oath_token)
    return redirect(redirect_url)


@app.route('/item-choice', methods=['POST'])
@require_login
def item_choice():
    """Store user selected product ID in session"""
    chosen_id = request.form.get('product_id')
    redirect_url = kroger_workflow.handle_item_choice(chosen_id)
    return redirect(redirect_url)


@app.route('/send-to-cart', methods=['POST', 'GET'])
@require_login
def kroger_send_to_cart():
    """Add selected products to user's Kroger cart"""
    redirect_url = kroger_workflow.handle_send_to_cart(g.user.oath_token)
    return redirect(redirect_url)


@app.route('/skip-ingredient', methods=['POST'])
@require_login
def skip_ingredient():
    """Skip current ingredient and move to next one"""
    if kroger_session_manager.has_more_ingredients():
        return redirect(url_for('kroger_product_search'))
    else:
        return redirect(url_for('kroger_send_to_cart'))


# User management routes
@app.route('/')
def homepage():
    """Landing page"""
    # Clear selected recipe IDs on page reload
    session.pop('selected_recipe_ids', None)

    form = AddRecipeForm()
    return render_template('index.html', form=form)


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
        return redirect(url_for('homepage'))
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
    return redirect(url_for('homepage'))


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
    return redirect(url_for('homepage'))


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

        recipe = Recipe.create_recipe(ingredients_text, url, user_id, name, notes)

        try:
            db.session.add(recipe)
            db.session.commit()
            flash('Recipe created successfully!', 'success')
            return redirect(url_for('homepage'))
        except Exception as error:
            db.session.rollback()
            flash('Error Occurred. Please try again', 'danger')
            return redirect(url_for('homepage'))
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

        for ingredient in recipe.recipe_ingredients:
            db.session.delete(ingredient)

        Recipe.parse_and_add_ingredients(recipe, form.ingredients_text.data)

        try:
            db.session.commit()
            flash('Recipe updated successfully!', 'success')
            return redirect(url_for('homepage'))
        except Exception as error:
            db.session.rollback()
            flash('Error occurred. Please try again', 'danger')
            print(error)

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
def update_grocery_list():
    """Add selected recipes to current grocery list"""
    selected_recipe_ids = request.form.getlist('recipe_ids')
    session['selected_recipe_ids'] = selected_recipe_ids

    grocery_list = g.grocery_list
    GroceryList.update_grocery_list(selected_recipe_ids, grocery_list=grocery_list)
    return redirect(url_for('homepage'))


@app.route('/clear_grocery_list', methods=['POST'])
@require_login
def clear_grocery_list():
    """Clear all items from the current grocery list"""
    grocery_list = g.grocery_list

    if grocery_list:
        grocery_list.recipe_ingredients.clear()
        db.session.commit()
        flash('Grocery list cleared successfully!', 'success')
    else:
        flash('No grocery list found', 'error')

    return redirect(url_for('homepage'))


@app.route('/add_manual_ingredient', methods=['POST'])
@require_login
def add_manual_ingredient():
    """Add a manually entered ingredient to the grocery list"""
    ingredient_text = request.form.get('ingredient_text', '').strip()

    if not ingredient_text:
        flash('Please enter an ingredient', 'error')
        return redirect(url_for('homepage'))

    try:
        # Parse the ingredient using the same logic as recipes
        parsed_ingredients = Recipe.parse_ingredients(ingredient_text)

        if not parsed_ingredients:
            flash('Could not parse ingredient. Please use format like "2 cups flour"', 'error')
            return redirect(url_for('homepage'))

        grocery_list = g.grocery_list

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

            # Convert quantity to float
            if "/" in quantity_string:
                from fractions import Fraction
                quantity = float(Fraction(quantity_string))
            elif Recipe.is_float(quantity_string):
                quantity = float(quantity_string)
            else:
                flash(f'Invalid quantity for ingredient: {ingredient_data["ingredient_name"]}', 'error')
                continue

            ingredient_name = ingredient_data["ingredient_name"]
            measurement = ingredient_data["measurement"]

            # Check if we can combine with existing ingredient
            combined = False
            for existing_entry in existing_ingredients[ingredient_name]:
                if existing_entry["measurement"] == measurement:
                    # Update existing ingredient quantity
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

    except Exception as e:
        db.session.rollback()
        flash('Error adding ingredient. Please try again.', 'error')

    return redirect(url_for('homepage'))


# Email functionality
@app.route('/email-modal', methods=['GET', 'POST'])
def email_modal():
    """Show email modal"""
    session['show_modal'] = True
    return redirect(url_for('homepage'))


@app.route('/send-email', methods=['POST'])
def send_grocery_list_email():
    """Send grocery list to user supplied email"""
    email = request.form['email']
    grocery_list = g.grocery_list

    if grocery_list:
        GroceryList.send_email(email, grocery_list, mail)
        flash("List sent successfully!", "success")
    else:
        flash("No grocery list found", "error")

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
        print(f"Error standardizing ingredients: {e}")
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


@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""
    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])
    else:
        g.user = None

@app.before_request
def add_grocery_list_to_g():
    """Add current grocery list to Flask global."""
    if g.user:
        # Get or create grocery list for the user
        grocery_list = GroceryList.query.filter_by(user_id=g.user.id).first()
        if not grocery_list:
            grocery_list = GroceryList(user_id=g.user.id)
            db.session.add(grocery_list)
            db.session.commit()
        g.grocery_list = grocery_list
        session[CURR_GROCERY_LIST_KEY] = grocery_list.id
    else:
        g.grocery_list = None


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
