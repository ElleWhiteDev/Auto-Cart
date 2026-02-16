# Refactoring Example - Before & After

This document shows concrete examples of how to refactor existing routes using the new improvements.

## Example 1: Kroger Product Search Route

### ❌ Before (Old Pattern)
```python
@app.route("/product-search", methods=["GET", "POST"])
@require_login
def kroger_product_search():
    """Search Kroger for ingredients based on name and present user with options."""
    kroger_user = get_household_kroger_user(g.household, g.user)
    is_valid, error_msg = validate_kroger_connection(kroger_user)

    if not is_valid:
        flash(error_msg, "danger")
        return redirect(url_for("homepage"))

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
            return redirect(url_for("homepage") + "#modal-ingredient")

    # Default behavior - search for next ingredient
    redirect_url = kroger_workflow.handle_product_search(kroger_user.oauth_token)
    return redirect(redirect_url)
```

### ✅ After (New Pattern)
```python
from constants import SessionKeys
from services.kroger_validation_service import require_kroger_connection

@app.route("/product-search", methods=["GET", "POST"])
@require_login
@require_kroger_connection  # Handles all validation automatically
def kroger_product_search():
    """Search Kroger for ingredients based on name and present user with options."""
    # g.kroger_user is now available from decorator
    
    # Handle custom search if provided
    if request.method == "POST":
        custom_search = request.form.get("custom_search", "").strip()
        if custom_search:
            # Perform custom search
            from kroger import parse_kroger_products

            response = kroger_service.search_products(
                custom_search, 
                session.get(SessionKeys.LOCATION_ID), 
                g.kroger_user.oauth_token
            )
            if response:
                products = parse_kroger_products(response)
                # Get current ingredient detail or create a generic one
                current_ingredient = session.get(
                    SessionKeys.CURRENT_INGREDIENT_DETAIL,
                    {"name": custom_search, "quantity": "1", "measurement": "unit"},
                )
                kroger_session_manager.store_product_choices(
                    products, current_ingredient
                )
            return redirect(url_for("homepage") + "#modal-ingredient")

    # Default behavior - search for next ingredient
    redirect_url = kroger_workflow.handle_product_search(g.kroger_user.oauth_token)
    return redirect(redirect_url)
```

**Improvements**:
- ✅ Removed 5 lines of duplicate validation code
- ✅ Using `SessionKeys` constants instead of magic strings
- ✅ Cleaner, more readable code
- ✅ Consistent with other Kroger routes

---

## Example 2: Recipe Creation Route

### ❌ Before (Old Pattern)
```python
@app.route('/recipes/add', methods=['POST'])
@require_login
def add_recipe():
    """Add a recipe to the database"""
    form = AddRecipeForm()
    
    if form.validate_on_submit():
        name = form.name.data
        ingredients_text = form.ingredients_text.data
        url = form.url.data
        notes = form.notes.data
        user_id = g.user.id
        visibility = request.form.get('visibility', 'private')

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
```

### ✅ After (New Pattern)
```python
from constants import FlashCategory, SuccessMessages, ErrorMessages, RecipeVisibility
from services.recipe_service import RecipeService

@app.route('/recipes/add', methods=['POST'])
@require_login
def add_recipe():
    """Add a recipe to the database"""
    form = AddRecipeForm()
    
    if form.validate_on_submit():
        visibility = request.form.get('visibility', RecipeVisibility.PRIVATE)
        
        # Use service layer - handles all transaction management
        recipe, error = RecipeService.create_recipe(
            household_id=g.household.id if g.household else None,
            name=form.name.data,
            ingredients_text=form.ingredients_text.data,
            url=form.url.data,
            notes=form.notes.data,
            created_by_user_id=g.user.id,
            visibility=visibility
        )
        
        if error:
            flash(error, FlashCategory.DANGER)
        else:
            flash(SuccessMessages.RECIPE_CREATED, FlashCategory.SUCCESS)
        
        return redirect(url_for('homepage'))
    else:
        logger.warning(f"Form validation failed: {form.errors}")
        flash(ErrorMessages.FORM_VALIDATION_FAILED, FlashCategory.DANGER)
        return redirect(url_for('homepage'))
```

**Improvements**:
- ✅ Removed 15 lines of transaction management code
- ✅ Using constants for all messages and categories
- ✅ Service layer handles all database operations
- ✅ Cleaner error handling
- ✅ More testable (can mock service layer)

---

## Example 3: Login Route

### ❌ Before (Old Pattern)
```python
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.authenticate(form.username.data, form.password.data)
        
        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", "success")
            return redirect(url_for('homepage'))
        
        flash("Invalid credentials.", 'danger')
    
    return render_template('login.html', form=form)
```

### ✅ After (New Pattern)
```python
from constants import FlashCategory, ErrorMessages

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.authenticate(form.username.data, form.password.data)
        
        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", FlashCategory.SUCCESS)
            return redirect(url_for('homepage'))
        
        flash(ErrorMessages.INVALID_CREDENTIALS, FlashCategory.DANGER)
    
    return render_template('login.html', form=form)
```

**Improvements**:
- ✅ Using `FlashCategory` enum instead of magic strings
- ✅ Using `ErrorMessages` constant for consistency
- ✅ Easy to update message globally

---

## Migration Checklist

When refactoring a route, follow these steps:

### 1. Import New Modules
```python
from constants import FlashCategory, ErrorMessages, SuccessMessages, SessionKeys
from services.kroger_validation_service import require_kroger_connection
from services.base_service import BaseService
```

### 2. Replace Magic Strings
- [ ] Flash categories: `"danger"` → `FlashCategory.DANGER`
- [ ] Error messages: `"Error message"` → `ErrorMessages.CONSTANT_NAME`
- [ ] Success messages: `"Success!"` → `SuccessMessages.CONSTANT_NAME`
- [ ] Session keys: `"key_name"` → `SessionKeys.KEY_NAME`

### 3. Add Decorators
- [ ] Kroger routes: Add `@require_kroger_connection`
- [ ] Remove manual Kroger validation code

### 4. Use Service Layer
- [ ] Replace direct database operations with service methods
- [ ] Remove try/except/commit/rollback blocks
- [ ] Handle service return values (tuple of result, error)

### 5. Test
- [ ] Verify route still works
- [ ] Check error handling
- [ ] Verify flash messages display correctly

---

## Common Patterns

### Pattern 1: Flash Message
```python
# Before
flash("Some message", "danger")

# After
flash(ErrorMessages.SOME_ERROR, FlashCategory.DANGER)
```

### Pattern 2: Session Access
```python
# Before
user_id = session.get("curr_user")
products = session.get("products_for_cart", [])

# After
user_id = session.get(SessionKeys.CURR_USER)
products = session.get(SessionKeys.PRODUCTS_FOR_CART, [])
```

### Pattern 3: Database Operation
```python
# Before
try:
    obj = Model(...)
    db.session.add(obj)
    db.session.commit()
    return obj, None
except Exception as e:
    db.session.rollback()
    logger.error(f"Error: {e}", exc_info=True)
    return None, "Error message"

# After
def create_operation():
    obj = Model(...)
    db.session.add(obj)
    return obj

return BaseService.execute_with_transaction(
    create_operation,
    ErrorMessages.SOME_ERROR,
    "operation name"
)
```

