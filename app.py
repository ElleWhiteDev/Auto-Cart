import base64
import requests
import json
from urllib.parse import urlencode
from flask import Flask, render_template, request, flash, redirect, session, g, url_for
from flask_mail import Mail, Message
from sqlalchemy.exc import IntegrityError
from flask_bcrypt import Bcrypt
from functools import wraps
from models import db, connect_db, User, Recipe, GroceryList
from forms import UserAddForm, AddRecipeForm, UpdatePasswordForm, LoginForm, UpdateEmailForm
from secret import CLIENT_ID, OAUTH2_BASE_URL, API_BASE_URL, REDIRECT_URL, CLIENT_SECRET

CURR_USER_KEY = "curr_user"
CURR_GROCERY_LIST_KEY = "curr_grocery_list"

app = Flask(__name__)
bcrypt = Bcrypt(app)

#app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql:///auto_cart'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgres:///vhmyfvagwjinim:1c188fe0a55e2dcf8d9dd0e14f3a4f019f09661a0ecde466f9c123637f515da5@ec2-54-167-29-148.compute-1.amazonaws.com:5432/d15jd43h78a304'




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

#################################################

# @app.route('/authenticate')
# @require_login
# def kroger_authenticate():
#     """Redirect user to Kroger API for authentication"""

#     if g.user.oath_token:
#         print("ALREADY AUTHENTICATED REDIRECTING")
#         return redirect(url_for('callback'))
#     url = get_kroger_auth_url()
#     print("AUTHENTICATING REDIRECTING")
#     return redirect(url)


# def get_kroger_auth_url():
#     """Generate the URL for the Kroger OAuth2 flow."""

#     scope = 'cart.basic:write product.compact profile.compact'
#     params = {
#         'client_id': CLIENT_ID,
#         'redirect_uri': REDIRECT_URL,
#         'response_type': 'code',
#         'scope': scope
#     }
#     url = f"{OAUTH2_BASE_URL}/authorize?{urlencode(params)}"
#     return url


# @app.route('/callback')
# @require_login
# def callback():
#     """Receive bearer token and profile ID from Kroger API."""
#     authorization_code = request.args.get('code')
#     user = g.user

#     if user.oath_token:
#         try:
#             new_oath_token, refresh_token = refresh_kroger_access_token(user.refresh_token)
#             if new_oath_token:
#                 user.oath_token = new_oath_token
#                 user.refresh_token = refresh_token
#             else:
#                 print("Failed to refresh token. Keeping old token.")
#         except Exception as e:
#             print(f"An error occurred while refreshing the token: {e}")
#     else:
#         try:
#             access_token, refresh_token = get_kroger_access_token(authorization_code)
#             profile_id = fetch_kroger_profile_id(access_token)
#             user.oath_token = access_token
#             user.refresh_token = refresh_token
#             user.profile_id = profile_id
#         except Exception as e:
#             print(f"An error occurred while fetching the new token: {e}")

#     db.session.commit()

#     session['show_modal'] = True


#     form = AddRecipeForm()
#     return redirect(url_for('homepage', form=form) + '#modal-zipcode')


# def get_kroger_access_token(authorization_code):
#     """Exchange the authorization code for an access token."""

#     client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
#     encoded_credentials = base64.b64encode(client_credentials.encode()).decode()
#     scope = 'cart.basic:write product.compact profile.compact'
#     headers = {
#         'Authorization': f'Basic {encoded_credentials}',
#         'Content-Type': 'application/x-www-form-urlencoded'
#     }

#     body = urlencode({
#         'grant_type': 'authorization_code',
#         'code': authorization_code,
#         'redirect_uri': REDIRECT_URL,
#         'scope': scope
#     })

#     token_url = 'https://api.kroger.com/v1/connect/oauth2/token'
#     token_response = requests.post(token_url, data=body, headers=headers)

#     response_json = token_response.json()
#     access_token = response_json.get('access_token')
#     refresh_token = response_json.get('refresh_token')
#     return access_token, refresh_token


# def refresh_kroger_access_token(existing_token):
#     """Refresh the Kroger access token."""
    
#     client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
#     encoded_credentials = base64.b64encode(client_credentials.encode()).decode()

    
#     headers = {
#         'Authorization': f'Basic {encoded_credentials}',
#         'Content-Type': 'application/x-www-form-urlencoded'
#     }
    
#     body = urlencode({
#         'grant_type': 'refresh_token',
#         'refresh_token': existing_token
#     })
    
#     token_url = 'https://api.kroger.com/v1/connect/oauth2/token'

#     token_response = requests.post(token_url, data=body, headers=headers)
    
#     new_oath_token = token_response.json().get('access_token')
#     refreshed_token = token_response.json().get('refresh_token')
    
#     return new_oath_token, refreshed_token


# def fetch_kroger_profile_id(token):
#     """Fetch the Kroger Profile ID."""
#     profile_url = 'https://api.kroger.com/v1/identity/profile'
#     headers = {
#         'Accept': 'application/json',
#         'Authorization': f'Bearer {token}'
#     }

#     profile_response = requests.get(profile_url, headers=headers)

#     if profile_response.status_code == 200:
#         return profile_response.json()['data']['id']
#     else:
#         print("Failed to get profile ID:", profile_response.content)
#         return None


# @app.route('/location-search', methods=['POST'])
# @require_login
# def location_search():
#     """Send request to Kroger API for locations"""

#     zipcode = request.form.get('zipcode')

#     token = g.user.oath_token

#     stores = fetch_kroger_stores(zipcode, token)
#     form = AddRecipeForm()

#     if stores:
#         session['stores'] = stores

#         return redirect(url_for('homepage', form=form) + '#modal-store')
#     else:
#         return redirect(url_for('homepage', form=form) + '#modal-store')


# def fetch_kroger_stores(zipcode, token):
#     API_URL = "https://api.kroger.com/v1/locations"
#     params = {
#         "filter.zipCode.near": zipcode,
#         "filter.limit": 5,
#         "filter.chain": "Kroger"
#     }

#     headers = {
#         'Accept': 'application/json',
#         'Authorization': f'Bearer {token}'
#     }

#     response = requests.get(API_URL, params=params, headers=headers)

#     if response.status_code == 200:
#         stores = []

#         for store in response.json()['data']:
#             address = store['address']['addressLine1']
#             city = store['address']['city']
#             location_id = store['locationId']
#             stores.append((address, city, location_id))


#         return stores
#     else:

#         return None


# @app.route('/select-store', methods=['POST'])
# @require_login
# def select_store():
#     """Store user selected store ID in session"""
    
#     store_id = request.form.get('store_id')
#     session['location_id'] = store_id


#     return redirect(url_for('search_kroger_products'))


# @app.route('/product-search')
# @require_login
# def search_kroger_products():
#     """Search Kroger for ingredients based on name and present user with options."""

#     if not session.get('ingredient_names'):
#         ingredient_names = [ingredient.ingredient_name for ingredient in g.grocery_list.recipe_ingredients]
#         session['ingredient_names'] = ingredient_names
    
#     next_ingredient = session['ingredient_names'].pop(0) if session['ingredient_names'] else None
#     if next_ingredient:
#         response = get_kroger_products(next_ingredient)
#         if response:
#             session['items_to_choose_from'] = parse_product_response(response)
#     form = AddRecipeForm()
#     return redirect(url_for('homepage', form=form) + '#modal-ingredient')


# def parse_product_response(json_response):
#     """Parse Kroger response for customer selection."""

#     """Parse Kroger response for customer selection."""
    
#     # Navigate to the 'data' key first, then iterate through the list of products
#     products_data = json_response.get('data', [])
#     items_to_choose_from = []
    
#     for product_data in products_data:
#         product = {
#             'name': product_data.get('description', 'N/A'),
#             'id': product_data.get('upc', 'N/A'),
#             'price': product_data.get('items', [{}])[0].get('price', {}).get('regular', 'N/A')
#         }
#         items_to_choose_from.append(product)
    
#     return items_to_choose_from


# def get_kroger_products(ingredient):
#     """Fetch Kroger products based on the ingredient."""
#     BEARER_TOKEN = g.user.oath_token
#     LOCATION_ID = session.get('location_id')

#     api_url = f"https://api.kroger.com/v1/products?filter.term={ingredient}&filter.locationId={LOCATION_ID}&filter.limit=10"
        
#     headers = {
#         'Accept': 'application/json',
#         'Authorization': f'Bearer {BEARER_TOKEN}'
#     }

#     response = requests.get(api_url, headers=headers)

#     if response.status_code == 200:
#         return response.json()
#     else:
#         print(f"Failed to fetch data for ingredient: {ingredient}")
#         return None


# @app.route('/item-choice', methods=['POST'])
# @require_login
# def item_choice():
#     """Store user selected product ID in session"""

#     chosen_id = request.form.get('product_id')


#     for item in session.get('items_to_choose_from', []):
#         if item['id'] == chosen_id:
#             session['products_for_cart'].append(item['id'])

#             session['items_to_choose_from'] = []


#     if session.get('ingredient_names'):

#         return redirect(url_for('search_kroger_products'))
#     else:

#         return redirect(url_for('send_to_cart'))


# @app.route('/send-to-cart', methods=['POST', 'GET'])
# @require_login
# def send_to_cart():
#     """Add selected products to user's Kroger cart"""

#     selected_upcs = session.get('products_for_cart', [])
#     items = [{"quantity": 1, "upc": upc, "modality": "instore"} for upc in selected_upcs]

#     success = add_to_cart(items)

#     session['products_for_cart'] = []
#     session['items_to_choose_from'] = []
#     session['show_modal'] = False
#     session['location_id'] = None
#     session['stores'] = []
    
#     if success:
#         return redirect('https://www.kroger.com/cart')
#     else:
#         form = AddRecipeForm()
#         return redirect(url_for('homepage', form=form))


# def add_to_cart(items):
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
def send_email():
    email = request.form['email']
    list_content = format_grocery_list(g.grocery_list)
    send_email(email, list_content)
    flash("List sent successfully!", "success")
    return redirect(url_for('homepage'))


def send_email(recipient, content):
    msg = Message("Your List", recipients=[recipient])
    msg.body = f"Here is your list:\n{content}"
    mail.send(msg)

def format_grocery_list(grocery_list):
    ingredients_list = []
    for recipe_ingredient in grocery_list.recipe_ingredients:
        ingredient_detail = f"{recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}"
        ingredients_list.append(ingredient_detail)

    return "\n".join(ingredients_list)

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
    """User submits chunk of text. It's parsed into individual ingregient objects and assembled into a recipe"""

    form = AddRecipeForm()

    if form.validate_on_submit():
        name = form.name.data
        ingredients_text = form.ingredients_text.data
        url = form.url.data
        notes = form.notes.data
        user_id=g.user.id
        
        recipe = Recipe.create_recipe(ingredients_text, url, user_id, name, notes)

        try:
            db.session.add(recipe)
            db.session.commit()

            flash('Recipe created successfully!', 'success')
            return redirect(url_for('homepage', form=form))
        except Exception as error:
            db.session.rollback()
            flash('Error Occured. Please try again', 'danger')
            print(error)
            return redirect(url_for('homepage', form=form))
    return redirect(url_for('homepage', form=form))


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
        form.populate_obj(recipe)
        recipe.recipe_ingredients = Recipe.parse_ingredients(form.ingredient_text.data)
        
        try:
            db.session.commit()
            flash('Recipe updated successfully!', 'success')
        except Exception as error:
            db.session.rollback()
            flash('Error occurred. Please try again.', 'danger')
            print(error)

    return render_template('recipe.html', recipe=recipe, form=form)

    

@app.route('/update_grocery_list', methods=['POST'])
def update_grocery_list():
    """Add selected recipes to current grocery list"""
    
    selected_recipe_ids = request.form.getlist('recipe_ids')
    session['selected_recipe_ids'] = selected_recipe_ids

    grocery_list = g.grocery_list
    GroceryList.update_grocery_list(selected_recipe_ids, grocery_list=grocery_list)
    return redirect(url_for('homepage'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
