import base64
import requests
from urllib.parse import urlencode
from flask import Flask, render_template, request, flash, redirect, session, g, url_for
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

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql:///auto_cart'
# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://eawhite:koneko13@magiccartdb.crrapbdvxpld.us-east-2.rds.amazonaws.com:5432/magiccartdb'



app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False
app.config['SECRET_KEY'] = 'keep it secret keep it safe'

app.app_context().push()
connect_db(app)


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
        print('user detected:', g.user)
        user = g.user

        recipes = Recipe.query.filter_by(user_id=user.id).all()
        print(recipes)
        grocery_lists = GroceryList.query.filter_by(user_id=user.id).all()
        print(grocery_lists)

        grocery_list_recipe_ingredients = []
        for grocery_list in grocery_lists:
            grocery_list_recipe_ingredients.extend(grocery_list.recipe_ingredients)

        selected_recipe_ids = session.get('selected_recipe_ids', [])

        print('grocery list ingredients', grocery_list_recipe_ingredients)
        return {
            'grocery_lists': grocery_lists,
            'recipes': recipes,
            'grocery_list_recipe_ingredients': grocery_list_recipe_ingredients,
            'selected_recipe_ids': selected_recipe_ids
        }

    else:
        print('no user detected')
    return {}


#################################################

@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""

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

@app.route('/authenticate')
@require_login
def kroger_authenticate():
    """Send request to Kroger API for authentication token"""
        # Must define all scopes needed for application
    scope = 'cart.basic:write product.compact profile.compact'

    # Build authorization URL
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URL,
        'response_type': 'code',
        'scope': scope
    }
    url = f"{OAUTH2_BASE_URL}/authorize?{urlencode(params)}"

    # Redirect to the OAuth2 /authorize page (if using Flask)
    return redirect(url)
    

@app.route('/callback')
@require_login
def callback():
    """Recieve bearer token from Kroger API"""

    authorization_code = request.args.get('code')

    # Prepare the authorization header
    client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(client_credentials.encode()).decode()
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    # Prepare the request body
    body = urlencode({
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri': REDIRECT_URL
    })

    # Make the token request
    token_url = 'https://api.kroger.com/v1/connect/oauth2/token'
    token_response = requests.post(token_url, data=body, headers=headers)

    # Extract the access token from the response
    access_token = token_response.json().get('access_token')

    # Store the access token
    user = g.user
    user.oath_token = access_token

    db.session.commit()

    form = AddRecipeForm()
    return redirect(url_for('homepage', form=form))

#################################################

@app.route('/product-search')
def search_kroger_product(name, token):
    """Choose product from Kroger and get product ID"""

    base_url = "https://api.kroger.com/v1/products"
    headers = {
        'Accept' : 'application/json',
        'Authorization' : f'Bearer {token}'
    }
    params = {
        'filter.term' : name
    }

    response = requests.get(base_url, headers=headers, params=params)

    selection_list = parse_kroger_response(response)

    return selection_list

def parse_kroger_response(response):
    """Parse Kroger response for customer selection"""

    products = []
    for product in response['data']:
        products.append({
            'name' : product.get['description', 'N/A'],
            'id' : product.get['productId', 'N/A'],
            'price' : product.get['items'][0].get('price', {}).get('regular', 'N/A')
        })
    
    return products

#################################################

@app.route('/')
def homepage():
    """Landing page"""

    form = AddRecipeForm()

    return render_template('home.html', form=form)


@app.route('/register', methods=["GET", "POST"])
def register():
    """Handle user signup"""

    form = UserAddForm()

    print(form.errors)

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
        user = User.authenticate(form.username.data,
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

    flash('Successfully logged out', 'success')
    return redirect(url_for('login'))


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
    return redirect(url_for('login'))

##########################################################

@app.route('/add_recipe', methods=["GET","POST"])
def add_recipe():
    """User submits chunk of text. It's parsed into individual ingregient objects and assembled into a recipe"""

    form = AddRecipeForm()

    if form.validate_on_submit():
        name = form.name.data
        ingredients_text = form.ingredients_text.data
        url = form.url.data
        user_id=g.user.id
        
        recipe = Recipe.create_recipe(ingredients_text, url, user_id, name)

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
    form = AddRecipeForm(obj=recipe)

    if form.validate_on_submit():
        form.populate_obj(recipe)

        try:
            db.session.add(recipe)
            db.session.commit()

            flash('Recipe created successfully!', 'success')
            return redirect(url_for('view_recipe', recipe_id=recipe.id), form=form)
            
        except Exception as error:
            db.session.rollback()
            flash('Error Occured. Please try again', 'danger')
            print(error)
            return redirect(url_for('view_recipe', recipe_id=recipe.id), form=form)

    return render_template('recipe.html', recipe_id=recipe_id, form=form)


@app.route('/grocery_list', methods=["GET", "POST"])
def view_gorcery_list(recipe_id):
    """View/Edit a user built grocery list"""

    return render_template('recipe.html', recipe_id=recipe_id)
    

@app.route('/update_grocery_list', methods=['POST'])
def update_grocery_list():
    """Add selected recipes to current grocery list"""
    
    selected_recipe_ids = request.form.getlist('recipe_ids')
    session['selected_recipe_ids'] = selected_recipe_ids

    grocery_list = g.grocery_list
    GroceryList.update_grocery_list(selected_recipe_ids, grocery_list=grocery_list)
    return redirect(url_for('homepage'))
