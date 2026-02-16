# Quick Reference Guide - Code Improvements

## 🚀 Quick Start

### Import the New Modules
```python
from constants import (
    FlashCategory, 
    ErrorMessages, 
    SuccessMessages, 
    SessionKeys,
    MealType,
    RecipeVisibility
)
from services.base_service import BaseService
from services.kroger_validation_service import require_kroger_connection
```

---

## 📝 Common Replacements

### Flash Messages
```python
# ❌ Old
flash("Error message", "danger")
flash("Success message", "success")

# ✅ New
flash(ErrorMessages.SOME_ERROR, FlashCategory.DANGER)
flash(SuccessMessages.SOME_SUCCESS, FlashCategory.SUCCESS)
```

### Session Keys
```python
# ❌ Old
user_id = session.get("curr_user")
products = session.get("products_for_cart", [])

# ✅ New
user_id = session.get(SessionKeys.CURR_USER)
products = session.get(SessionKeys.PRODUCTS_FOR_CART, [])
```

### Meal Type Validation
```python
# ❌ Old
valid_meal_types = ["breakfast", "lunch", "dinner", "snack"]
if meal_type.lower() not in valid_meal_types:
    return None, f"Invalid meal type. Must be one of: {', '.join(valid_meal_types)}"

# ✅ New
if not MealType.is_valid(meal_type):
    return None, f"Invalid meal type. Must be one of: {', '.join(MealType.values())}"
```

---

## 🎯 Decorator Usage

### Kroger Routes
```python
# ❌ Old
@app.route('/some-kroger-route')
@require_login
def some_kroger_route():
    kroger_user = get_household_kroger_user(g.household, g.user)
    is_valid, error_msg = validate_kroger_connection(kroger_user)
    if not is_valid:
        flash(error_msg, "danger")
        return redirect(url_for("homepage"))
    # ... rest of route

# ✅ New
@app.route('/some-kroger-route')
@require_login
@require_kroger_connection
def some_kroger_route():
    # g.kroger_user is automatically available
    # ... rest of route
```

---

## 💾 Database Operations

### Create Operation
```python
# ❌ Old
try:
    obj = Model(field1=value1, field2=value2)
    db.session.add(obj)
    db.session.commit()
    return obj, None
except Exception as e:
    db.session.rollback()
    logger.error(f"Error: {e}", exc_info=True)
    return None, "Error message"

# ✅ New
def create_operation():
    obj = Model(field1=value1, field2=value2)
    db.session.add(obj)
    return obj

return BaseService.execute_with_transaction(
    create_operation,
    ErrorMessages.SOME_ERROR,
    "operation description"
)
```

### Update Operation
```python
# ❌ Old
try:
    obj.field = new_value
    db.session.commit()
    return True, None
except Exception as e:
    db.session.rollback()
    logger.error(f"Error: {e}", exc_info=True)
    return False, "Error message"

# ✅ New
def update_operation():
    obj.field = new_value

return BaseService.execute_update_with_transaction(
    update_operation,
    "Error message",
    "operation description"
)
```

---

## 📋 Available Constants

### FlashCategory
- `FlashCategory.SUCCESS`
- `FlashCategory.DANGER`
- `FlashCategory.WARNING`
- `FlashCategory.INFO`
- `FlashCategory.ERROR`

### MealType
- `MealType.BREAKFAST`
- `MealType.LUNCH`
- `MealType.DINNER`
- `MealType.SNACK`
- Methods: `MealType.values()`, `MealType.is_valid(value)`

### RecipeVisibility
- `RecipeVisibility.PRIVATE`
- `RecipeVisibility.HOUSEHOLD`

### SessionKeys
- `SessionKeys.CURR_USER`
- `SessionKeys.CURR_GROCERY_LIST`
- `SessionKeys.SHOW_MODAL`
- `SessionKeys.PRODUCTS_FOR_CART`
- `SessionKeys.ITEMS_TO_CHOOSE_FROM`
- `SessionKeys.SELECTED_RECIPE_IDS`
- `SessionKeys.LOCATION_ID`
- `SessionKeys.CURRENT_INGREDIENT_DETAIL`

### ErrorMessages (Common)
- `ErrorMessages.LOGIN_REQUIRED`
- `ErrorMessages.ADMIN_REQUIRED`
- `ErrorMessages.INVALID_CREDENTIALS`
- `ErrorMessages.KROGER_CONNECTION_REQUIRED`
- `ErrorMessages.FORM_VALIDATION_FAILED`
- `ErrorMessages.DB_COMMIT_ERROR`
- `ErrorMessages.RECIPE_CREATE_ERROR`
- `ErrorMessages.GROCERY_LIST_CREATE_ERROR`

### SuccessMessages (Common)
- `SuccessMessages.RECIPE_CREATED`
- `SuccessMessages.RECIPE_UPDATED`
- `SuccessMessages.KROGER_CONNECTED`
- `SuccessMessages.PASSWORD_UPDATED`
- `SuccessMessages.EMAIL_UPDATED`

---

## 🛠️ BaseService Methods

### execute_with_transaction
For operations that return an object (create operations):
```python
result, error = BaseService.execute_with_transaction(
    operation_function,
    error_message,
    operation_name_for_logging
)
```

### execute_update_with_transaction
For operations that return success/failure (update/delete operations):
```python
success, error = BaseService.execute_update_with_transaction(
    operation_function,
    error_message,
    operation_name_for_logging
)
```

### safe_strip
Safely strip whitespace from strings:
```python
cleaned = BaseService.safe_strip(user_input)  # Returns None if empty
```

### validate_required_fields
Validate required fields:
```python
error = BaseService.validate_required_fields(
    name=name,
    email=email,
    password=password
)
if error:
    return None, error
```

---

## 🔍 When to Use What

### Use Constants When:
- ✅ Displaying flash messages
- ✅ Accessing session keys
- ✅ Validating meal types
- ✅ Setting recipe visibility
- ✅ Returning error messages

### Use BaseService When:
- ✅ Creating database records
- ✅ Updating database records
- ✅ Deleting database records
- ✅ Any operation requiring transaction management

### Use Decorators When:
- ✅ Route requires Kroger connection
- ✅ Route requires authentication (existing `@require_login`)
- ✅ Route requires admin access (existing `@require_admin`)

---

## ⚠️ Common Mistakes to Avoid

### ❌ Don't Mix Old and New Patterns
```python
# Bad - mixing patterns
flash(ErrorMessages.SOME_ERROR, "danger")  # ❌ Mixed

# Good - consistent
flash(ErrorMessages.SOME_ERROR, FlashCategory.DANGER)  # ✅
```

### ❌ Don't Forget to Import
```python
# Bad - using without import
flash(ErrorMessages.LOGIN_REQUIRED, FlashCategory.DANGER)  # ❌ NameError

# Good - import first
from constants import ErrorMessages, FlashCategory
flash(ErrorMessages.LOGIN_REQUIRED, FlashCategory.DANGER)  # ✅
```

### ❌ Don't Bypass BaseService
```python
# Bad - manual transaction management in service
try:
    db.session.commit()  # ❌ Don't do this in services
except:
    db.session.rollback()

# Good - use BaseService
return BaseService.execute_with_transaction(...)  # ✅
```

---

## 📚 More Information

- **Detailed explanations**: See `CODE_IMPROVEMENTS.md`
- **Refactoring examples**: See `REFACTORING_EXAMPLE.md`
- **Full summary**: See `REVIEW_SUMMARY.md`

