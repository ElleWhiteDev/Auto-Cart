import base64
import os
import requests
import json
from fractions import Fraction
from urllib.parse import urlencode, urljoin, urlparse
from flask import Flask, render_template, request, flash, redirect, session, g, url_for, jsonify
from flask_mail import Mail, Message
from sqlalchemy.exc import IntegrityError
from flask_bcrypt import Bcrypt
from functools import wraps
from models import db, connect_db, User, Recipe, GroceryList, RecipeIngredient
from forms import UserAddForm, AddRecipeForm, UpdatePasswordForm, LoginForm, UpdateEmailForm
from secret import CLIENT_ID, OAUTH2_BASE_URL, API_BASE_URL, REDIRECT_URL, CLIENT_SECRET
from bs4 import BeautifulSoup
import re

CURR_USER_KEY = "curr_user"
CURR_GROCERY_LIST_KEY = "curr_grocery_list"

app = Flask(__name__)
bcrypt = Bcrypt(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql:///auto_cart'
# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://utrqjjxkwlrohb:ccc6e93157652b53c4998ba72c1bf6b0b73d43c05e4c9f13b8a81b5540219e2b@ec2-100-26-73-144.compute-1.amazonaws.com:5432/d2hhhk29b6cn4l'



app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False
app.config['SECRET_KEY'] = 'keep it secret keep it safe'

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'autocartgrocerylist@gmail.com'
app.config['MAIL_PASSWORD'] = 'lnriddicjzjfxjxt'
app.config['MAIL_DEFAULT_SENDER'] = 'sutocartgrocerylist@gmail.com'

mail = Mail(app)
mail.init_app(app)


connect_db(app)
with app.app_context():
    db.create_all()


def require_login(func):
    """Check user is logged in"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if CURR_USER_KEY not in session:
            flash('You must be logged in to view this page', 'danger')
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user_data():
    """Populate user data for homepage"""

    if hasattr(g, 'user') and g.user:
        user = g.user

        recipes = Recipe.query.filter_by(user_id=user.id).all()
        grocery_lists = GroceryList.query.filter_by(user_id=user.id).all()

        grocery_list_recipe_ingredients = []
        for grocery_list in grocery_lists:
            grocery_list_recipe_ingredients.extend(grocery_list.recipe_ingredients)

        selected_recipe_ids = session.get('selected_recipe_ids', [])

        return {
            'grocery_lists': grocery_lists,
            'recipes': recipes,
            'grocery_list_recipe_ingredients': grocery_list_recipe_ingredients,
            'selected_recipe_ids': selected_recipe_ids
        }
    else:
        return {}


#################################################

@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""

    if 'show_modal' not in session:
        session['show_modal'] = False

    if 'products_for_cart' not in session:
        session['products_for_cart'] = []

    if 'items_to_choose_from' not in session:
        session['items_to_choose_from'] = []

    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])

        g.grocery_list_id = session.get(CURR_GROCERY_LIST_KEY)

        if g.grocery_list_id is None and request.endpoint != 'edit_grocery_list':
            grocery_list = GroceryList(user_id=g.user.id)
            db.session.add(grocery_list)
            db.session.commit()
            session[CURR_GROCERY_LIST_KEY] = grocery_list.id
            g.grocery_list = grocery_list
        else:
            g.grocery_list = GroceryList.query.get(g.grocery_list_id)

    else:
        g.user = None
        g.grocery_list = None


def do_login(user):
    """Log in user."""

    session[CURR_USER_KEY] = user.id


def do_logout():
    """Logout user."""

    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]
        del session[CURR_GROCERY_LIST_KEY]

################################################

@app.route('/authenticate')
@require_login
def kroger_authenticate():
    """Redirect user to Kroger API for authentication"""

    if g.user.oath_token:
        print("ALREADY AUTHENTICATED REDIRECTING")
        return redirect(url_for('callback'))
    url = get_kroger_auth_url()
    print("AUTHENTICATING REDIRECTING")
    return redirect(url)


def get_kroger_auth_url():
    """Generate the URL for the Kroger OAuth2 flow."""

    scope = 'cart.basic:write product.compact profile.compact'
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URL,
        'response_type': 'code',
        'scope': scope
    }
    url = f"{OAUTH2_BASE_URL}/authorize?{urlencode(params)}"
    return url


@app.route('/callback')
@require_login
def callback():
    """Receive bearer token and profile ID from Kroger API."""
    authorization_code = request.args.get('code')
    user = g.user

    if user.oath_token:
        try:
            new_oath_token, refresh_token = refresh_kroger_access_token(user.refresh_token)
            if new_oath_token:
                user.oath_token = new_oath_token
                user.refresh_token = refresh_token
            else:
                print("Failed to refresh token. Keeping old token.")
        except Exception as e:
            print(f"An error occurred while refreshing the token: {e}")
    else:
        try:
            access_token, refresh_token = get_kroger_access_token(authorization_code)
            profile_id = fetch_kroger_profile_id(access_token)
            user.oath_token = access_token
            user.refresh_token = refresh_token
            user.profile_id = profile_id
        except Exception as e:
            print(f"An error occurred while fetching the new token: {e}")

    db.session.commit()

    session['show_modal'] = True


    form = AddRecipeForm()
    return redirect(url_for('homepage', form=form) + '#modal-zipcode')


def get_kroger_access_token(authorization_code):
    """Exchange the authorization code for an access token."""

    client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(client_credentials.encode()).decode()
    scope = 'cart.basic:write product.compact profile.compact'
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    body = urlencode({
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri': REDIRECT_URL,
        'scope': scope
    })

    token_url = 'https://api.kroger.com/v1/connect/oauth2/token'
    token_response = requests.post(token_url, data=body, headers=headers)

    response_json = token_response.json()
    access_token = response_json.get('access_token')
    refresh_token = response_json.get('refresh_token')
    return access_token, refresh_token


def refresh_kroger_access_token(existing_token):
    """Refresh the Kroger access token."""

    client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(client_credentials.encode()).decode()


    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    body = urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': existing_token
    })

    token_url = 'https://api.kroger.com/v1/connect/oauth2/token'

    token_response = requests.post(token_url, data=body, headers=headers)

    new_oath_token = token_response.json().get('access_token')
    refreshed_token = token_response.json().get('refresh_token')

    return new_oath_token, refreshed_token


def fetch_kroger_profile_id(token):
    """Fetch the Kroger Profile ID."""
    profile_url = 'https://api.kroger.com/v1/identity/profile'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    profile_response = requests.get(profile_url, headers=headers)

    if profile_response.status_code == 200:
        return profile_response.json()['data']['id']
    else:
        print("Failed to get profile ID:", profile_response.content)
        return None


@app.route('/location-search', methods=['POST'])
@require_login
def location_search():
    """Send request to Kroger API for locations"""

    zipcode = request.form.get('zipcode')

    token = g.user.oath_token

    stores = fetch_kroger_stores(zipcode, token)
    form = AddRecipeForm()

    if stores:
        session['stores'] = stores

        return redirect(url_for('homepage', form=form) + '#modal-store')
    else:
        return redirect(url_for('homepage', form=form) + '#modal-store')


def fetch_kroger_stores(zipcode, token):
    """Fetch Kroger stores based on zipcode"""
    API_URL = "https://api.kroger.com/v1/locations"
    params = {
        "filter.zipCode.near": zipcode,
        "filter.limit": 5,
        "filter.chain": "Kroger"
    }

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    response = requests.get(API_URL, params=params, headers=headers)

    if response.status_code == 200:
        stores = []

        for store in response.json()['data']:
            address = store['address']['addressLine1']
            city = store['address']['city']
            location_id = store['locationId']
            stores.append((address, city, location_id))

        return stores
    else:

        return None


@app.route('/select-store', methods=['POST'])
@require_login
def select_store():
    """Store user selected store ID in session"""

    store_id = request.form.get('store_id')
    session['location_id'] = store_id

    return redirect(url_for('search_kroger_products'))


@app.route('/product-search')
@require_login
def search_kroger_products():
    """Search Kroger for ingredients based on name and present user with options."""

    if not session.get('ingredient_names'):
        ingredient_names = [ingredient.ingredient_name for ingredient in g.grocery_list.recipe_ingredients]
        session['ingredient_names'] = ingredient_names

    next_ingredient = session['ingredient_names'].pop(0) if session['ingredient_names'] else None
    if next_ingredient:
        response = get_kroger_products(next_ingredient)
        if response:
            session['items_to_choose_from'] = parse_product_response(response)
    form = AddRecipeForm()
    return redirect(url_for('homepage', form=form) + '#modal-ingredient')


def parse_product_response(json_response):
    """Parse Kroger response for customer selection."""

    """Parse Kroger response for customer selection."""

    # Navigate to the 'data' key first, then iterate through the list of products
    products_data = json_response.get('data', [])
    items_to_choose_from = []

    for product_data in products_data:
        product = {
            'name': product_data.get('description', 'N/A'),
            'id': product_data.get('upc', 'N/A'),
            'price': product_data.get('items', [{}])[0].get('price', {}).get('regular', 'N/A')
        }
        items_to_choose_from.append(product)

    return items_to_choose_from


def get_kroger_products(ingredient):
    """Fetch Kroger products based on the ingredient."""
    BEARER_TOKEN = g.user.oath_token
    LOCATION_ID = session.get('location_id')

    api_url = f"https://api.kroger.com/v1/products?filter.term={ingredient}&filter.locationId={LOCATION_ID}&filter.limit=10"

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {BEARER_TOKEN}'
    }

    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch data for ingredient: {ingredient}")
        return None


@app.route('/item-choice', methods=['POST'])
@require_login
def item_choice():
    """Store user selected product ID in session"""

    chosen_id = request.form.get('product_id')


    for item in session.get('items_to_choose_from', []):
        if item['id'] == chosen_id:
            session['products_for_cart'].append(item['id'])

            session['items_to_choose_from'] = []


    if session.get('ingredient_names'):

        return redirect(url_for('search_kroger_products'))
    else:

        return redirect(url_for('send_to_cart'))


@app.route('/send-to-cart', methods=['POST', 'GET'])
@require_login
def send_to_cart():
    """Add selected products to user's Kroger cart"""

    selected_upcs = session.get('products_for_cart', [])
    items = [{"quantity": 1, "upc": upc, "modality": "instore"} for upc in selected_upcs]

    success = add_to_cart(items)

    session['products_for_cart'] = []
    session['items_to_choose_from'] = []
    session['show_modal'] = False
    session['location_id'] = None
    session['stores'] = []

    if success:
        return redirect('https://www.kroger.com/cart')
    else:
        form = AddRecipeForm()
        return redirect(url_for('homepage', form=form))


def add_to_cart(items):
    """Add selected items to user's Kroger cart"""
    oath_token = g.user.oath_token
    for item in items:
        item.update({
            'quantity': 1,  # or any dynamic value you prefer
            'allowSubstitutes': True,
            'specialInstructions': "",
            'modality': "PICKUP"
        })

    url = f'https://api.kroger.com/v1/cart/add'

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {oath_token}',
        'Content-Type': 'application/json'
    }

    data = {'items': items}

    response = requests.put(url, headers=headers, data=json.dumps(data))

    if 200 <= response.status_code < 300:
        print("Successfully added items to cart")
        return True
    else:
        print("Something went wrong, items may not have been added to card (status code: %s)" %response.status_code)
        return

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


#################################################


@app.route('/')
def homepage():
    """Landing page"""

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
            print(error)
            if "users_email_key" in str(error.orig):
                flash("Email already taken", 'danger')
            elif "users_username_key" in str(error.orig):
                flash("Username already taken", 'danger')
            else:
                flash("An error occurred. Please try again.", 'danger')
            return render_template('/register.html', form=form)

        do_login(user)

        form = AddRecipeForm()

        return redirect(url_for('homepage', form=form))

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

            form = AddRecipeForm()
            return redirect(url_for('homepage', form=form))

        flash("Invalid credentials.", 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    """Handle logout of user."""

    do_logout()


    form = AddRecipeForm()
    flash('Successfully logged out', 'success')
    return redirect(url_for('homepage', form=form))


@app.route('/profile')
@require_login
def user_view():
    """View/edit recipesc update account info or delete account"""

    user = g.user.id
    return render_template('profile.html', user=user)


@app.route('/update_account', methods=["GET", "POST"])
def update_password():
    """Update user password"""

    form = UpdatePasswordForm()

    if form.validate_on_submit():
        user = g.user

        if User.authenticate(user.username, form.old_password.data):
            user.password = bcrypt.generate_password_hash(form.new_password.data).decode('UTF-8')
            db.session.commit()

            flash('Password updated successfully!', 'success')
            return redirect(url_for('user_view'))
        else:
            flash('Incorrect password', 'danger')
            return redirect(url_for('user_view'))

    return render_template('update_password.html', form=form)


@app.route('/update_email', methods=["GET", "POST"])
def update_email():
    """Update user email"""

    form = UpdateEmailForm()

    if form.validate_on_submit():
        user = g.user

        if User.authenticate(user.username, form.password.data):
            user.email = form.email.data
            db.session.commit()

            flash('Email updated successfully!', 'success')
            return redirect(url_for('user_view'))
        else:
            flash('Incorrect password', 'danger')
            return redirect(url_for('user_view'))

    return render_template('update_email.html', form=form)



@app.route('/delete_account', methods=["POST"])
def delete_account():
    """Delete user account"""

    user = g.user
    do_logout()
    db.session.delete(user)
    db.session.commit()

    flash('Account deleted successfully', 'success')
    return redirect(url_for('homepage'))

##########################################################

@app.route('/add_recipe', methods=["GET","POST"])
def add_recipe():
    """User submits chunk of text. It's parsed into individual ingredient objects and assembled into a recipe"""

    form = AddRecipeForm()

    if form.validate_on_submit():
        name = form.name.data
        ingredients_text = form.ingredients_text.data
        url = form.url.data
        notes = form.notes.data
        user_id = g.user.id

        # Determine source type based on whether URL was used for extraction
        source_type = 'extracted' if url and url.strip() else 'manual'

        recipe = Recipe.create_recipe(ingredients_text, url, user_id, name, notes, source_type)

        try:
            db.session.add(recipe)
            db.session.commit()
            flash('Recipe created successfully!', 'success')
            return redirect(url_for('homepage'))
        except Exception as error:
            db.session.rollback()
            flash('Error Occurred. Please try again', 'danger')
            print(error)
            return redirect(url_for('homepage'))
    return redirect(url_for('homepage'))


@app.route('/recipe/<int:recipe_id>', methods=["GET", "POST"])
def view_recipe(recipe_id):
    """View/Edit a user submitted recipe"""

    recipe = Recipe.query.get_or_404(recipe_id)

    # Create the text representation of the ingredients
    ingredients_text = "\n".join(
        f"{ingr.quantity} {ingr.measurement} {ingr.ingredient_name}"
        for ingr in recipe.recipe_ingredients
    )

    form = AddRecipeForm(obj=recipe, ingredients_text=ingredients_text)

    if form.validate_on_submit():
        # Manually update recipe fields
        recipe.name = form.name.data
        recipe.url = form.url.data
        recipe.notes = form.notes.data

        # Clear existing ingredients
        for ingredient in recipe.recipe_ingredients:
            db.session.delete(ingredient)

        # Parse and create new ingredients
        parsed_ingredients = Recipe.parse_ingredients(form.ingredients_text.data)
        for ingredient_data in parsed_ingredients:
            quantity_string = ingredient_data["quantity"]
            if "/" in quantity_string:
                quantity = float(Fraction(quantity_string))
            elif Recipe.is_float(quantity_string):
                quantity = float(quantity_string)
            else:
                continue

            recipe_ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                quantity=quantity,
                measurement=ingredient_data["measurement"],
                ingredient_name=ingredient_data["ingredient_name"],
            )
            recipe.recipe_ingredients.append(recipe_ingredient)

        try:
            db.session.commit()
            flash('Recipe updated successfully!', 'success')
        except Exception as error:
            db.session.rollback()
            flash('Error occurred. Please try again.', 'danger')
            print(error)

    return render_template('recipe.html', recipe=recipe, form=form)


@app.route('/recipe/<int:recipe_id>/delete', methods=["POST"])
@require_login
def delete_recipe(recipe_id):
    """Delete a recipe"""

    recipe = Recipe.query.get_or_404(recipe_id)

    # Ensure user owns this recipe
    if recipe.user_id != g.user.id:
        flash('You can only delete your own recipes', 'danger')
        return redirect(url_for('homepage'))

    recipe_name = recipe.name  # Store name before deletion

    try:
        db.session.delete(recipe)
        db.session.commit()
        flash(f'Recipe "{recipe_name}" deleted successfully!', 'success')
    except Exception as error:
        db.session.rollback()
        flash('Error occurred while deleting recipe', 'danger')
        print(error)

    return redirect(url_for('homepage'))


@app.route('/update_grocery_list', methods=['POST'])
def update_grocery_list():
    """Add selected recipes to current grocery list"""

    selected_recipe_ids = request.form.getlist('recipe_ids')
    session['selected_recipe_ids'] = selected_recipe_ids

    grocery_list = g.grocery_list
    GroceryList.update_grocery_list(selected_recipe_ids, grocery_list=grocery_list)
    return redirect(url_for('homepage'))


@app.route('/extract-recipe-form', methods=['POST'])
@require_login
def extract_recipe_form():
    """Extract recipe data from URL using web scraping"""

    url = request.form.get('url')
    print(f"=== RECIPE EXTRACTION DEBUG ===")
    print(f"URL received: {url}")

    if not url:
        return jsonify({'success': False, 'error': 'URL is required for recipe extraction'}), 400

    # Scrape the recipe data
    recipe_data = scrape_recipe_data(url)

    print(f"Scraping result: {recipe_data}")

    if recipe_data.get('error'):
        return jsonify({'success': False, 'error': f"Could not extract recipe: {recipe_data['error']}"}), 400
    elif recipe_data.get('name') or recipe_data.get('ingredients'):
        # Return the extracted data as JSON
        extracted_data = {
            'name': recipe_data.get('name', ''),
            'ingredients_text': '\n'.join(recipe_data.get('ingredients', [])),
            'notes': recipe_data.get('instructions', ''),
            'url': url
        }

        print(f"Returning extracted data: {extracted_data}")
        return jsonify({'success': True, 'data': extracted_data})
    else:
        return jsonify({'success': False, 'error': 'No recipe data found on this page. Please enter manually.'}), 400


def scrape_recipe_data(url):
    """
    Scrape recipe data from a URL using multiple extraction methods.
    Returns: {"name": str, "ingredients": list, "instructions": str, "error": str|None}
    """

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        print(f"=== SCRAPING DEBUG ===")
        print(f"Fetching URL: {url}")

        # Fetch the webpage
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        print(f"Response status: {response.status_code}")
        print(f"Content length: {len(response.content)}")

        soup = BeautifulSoup(response.content, 'html.parser')

        # Method 1: JSON-LD structured data
        recipe_data = extract_jsonld_recipe(soup)
        if recipe_data:
            print("Found JSON-LD recipe data")
            return recipe_data

        # Method 2: Microdata
        recipe_data = extract_microdata_recipe(soup)
        if recipe_data:
            print("Found microdata recipe data")
            return recipe_data

        # Method 3: HTML patterns fallback
        recipe_data = extract_html_patterns(soup)
        if recipe_data:
            print("Found recipe data using HTML patterns")
            return recipe_data

        print("No recipe data found using any method")
        return {"name": "", "ingredients": [], "instructions": "", "error": "No recipe data found on this page"}

    except requests.exceptions.Timeout:
        return {"name": "", "ingredients": [], "instructions": "", "error": "Request timed out"}
    except requests.exceptions.RequestException as e:
        return {"name": "", "ingredients": [], "instructions": "", "error": f"Failed to fetch page: {str(e)}"}
    except Exception as e:
        print(f"Scraping error: {e}")
        return {"name": "", "ingredients": [], "instructions": "", "error": f"Error parsing page: {str(e)}"}


def extract_jsonld_recipe(soup):
    """Extract recipe from JSON-LD structured data"""
    try:
        scripts = soup.find_all('script', type='application/ld+json')

        for script in scripts:
            try:
                data = json.loads(script.string)

                # Handle both single objects and arrays
                if isinstance(data, list):
                    data = data[0] if data else {}

                # Look for Recipe type (can be nested)
                recipe = find_recipe_in_jsonld(data)
                if recipe:
                    return parse_jsonld_recipe(recipe)

            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    except Exception as e:
        print(f"JSON-LD extraction error: {e}")

    return None


def find_recipe_in_jsonld(data):
    """Recursively find Recipe object in JSON-LD data"""
    if isinstance(data, dict):
        if data.get('@type') == 'Recipe':
            return data
        # Check nested objects
        for value in data.values():
            if isinstance(value, (dict, list)):
                result = find_recipe_in_jsonld(value)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = find_recipe_in_jsonld(item)
            if result:
                return result
    return None


def parse_jsonld_recipe(recipe):
    """Parse recipe data from JSON-LD format"""
    try:
        name = recipe.get('name', '')

        # Extract ingredients
        ingredients = []
        recipe_ingredients = recipe.get('recipeIngredient', [])
        for ingredient in recipe_ingredients:
            if isinstance(ingredient, str):
                ingredients.append(ingredient.strip())
            elif isinstance(ingredient, dict):
                ingredients.append(ingredient.get('text', str(ingredient)))

        # Extract instructions
        instructions = []
        recipe_instructions = recipe.get('recipeInstructions', [])
        for instruction in recipe_instructions:
            if isinstance(instruction, str):
                instructions.append(instruction.strip())
            elif isinstance(instruction, dict):
                text = instruction.get('text') or instruction.get('name', '')
                if text:
                    instructions.append(text.strip())

        instructions_text = '\n'.join(f"{i+1}. {inst}" for i, inst in enumerate(instructions))

        if name or ingredients:
            return {
                "name": name,
                "ingredients": ingredients,
                "instructions": instructions_text,
                "error": None
            }

    except Exception as e:
        print(f"JSON-LD parsing error: {e}")

    return None


def extract_microdata_recipe(soup):
    """Extract recipe from microdata"""
    try:
        recipe_elem = soup.find(attrs={"itemtype": "http://schema.org/Recipe"}) or \
                     soup.find(attrs={"itemtype": "https://schema.org/Recipe"})

        if not recipe_elem:
            return None

        name = ""
        name_elem = recipe_elem.find(attrs={"itemprop": "name"})
        if name_elem:
            name = name_elem.get_text(strip=True)

        # Extract ingredients
        ingredients = []
        ingredient_elems = recipe_elem.find_all(attrs={"itemprop": "recipeIngredient"})
        for elem in ingredient_elems:
            text = elem.get_text(strip=True)
            if text:
                ingredients.append(text)

        # Extract instructions
        instructions = []
        instruction_elems = recipe_elem.find_all(attrs={"itemprop": "recipeInstructions"})
        for elem in instruction_elems:
            text = elem.get_text(strip=True)
            if text:
                instructions.append(text)

        instructions_text = '\n'.join(f"{i+1}. {inst}" for i, inst in enumerate(instructions))

        if name or ingredients:
            return {
                "name": name,
                "ingredients": ingredients,
                "instructions": instructions_text,
                "error": None
            }

    except Exception as e:
        print(f"Microdata extraction error: {e}")

    return None


def extract_html_patterns(soup):
    """Extract recipe using common HTML patterns"""
    try:
        name = ""
        ingredients = []
        instructions = ""

        # Extract recipe name
        name_selectors = [
            'h1.recipe-title', 'h1.entry-title', 'h1.post-title',
            'h2.recipe-title', 'h2.entry-title',
            '.recipe-header h1', '.recipe-header h2',
            'h1', 'h2'
        ]

        for selector in name_selectors:
            elem = soup.select_one(selector)
            if elem:
                name = elem.get_text(strip=True)
                if name and len(name) < 200:  # Reasonable title length
                    break

        # Extract ingredients
        ingredient_selectors = [
            '.ingredients li', '.recipe-ingredients li',
            'ul.ingredients li', '[class*="ingredient"] li',
            '.ingredient-list li', '.recipe-ingredient'
        ]

        for selector in ingredient_selectors:
            elems = soup.select(selector)
            if elems:
                for elem in elems:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 3:  # Filter out empty/short items
                        ingredients.append(text)
                if ingredients:
                    break

        # Extract instructions
        instruction_selectors = [
            '.instructions li', '.recipe-instructions li',
            'ol.instructions li', '[class*="instruction"] li',
            '.directions li', '.recipe-directions li',
            '.method li', '.preparation li'
        ]

        instruction_steps = []
        for selector in instruction_selectors:
            elems = soup.select(selector)
            if elems:
                for elem in elems:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 10:  # Filter out short instructions
                        instruction_steps.append(text)
                if instruction_steps:
                    break

        if instruction_steps:
            instructions = '\n'.join(f"{i+1}. {step}" for i, step in enumerate(instruction_steps))

        # Return data if we found something useful
        if name or ingredients or instruction_steps:
            return {
                "name": name or "Untitled Recipe",
                "ingredients": ingredients,
                "instructions": instructions,
                "error": None
            }

    except Exception as e:
        print(f"HTML pattern extraction error: {e}")

    return None


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


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
