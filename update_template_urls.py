"""
Script to update url_for() calls in templates to use blueprint names.
"""

import os
import re

# Mapping of old route names to new blueprint.route names
ROUTE_MAPPING = {
    # Main blueprint routes
    'homepage': 'main.homepage',
    'household_setup': 'main.household_setup',
    'create_household': 'main.create_household',
    'switch_household': 'main.switch_household',
    
    # Auth blueprint routes
    'register': 'auth.register',
    'login': 'auth.login',
    'logout': 'auth.logout',
    'user_view': 'auth.profile',
    'update_username': 'auth.update_username',
    'update_email': 'auth.update_email',
    'update_password': 'auth.update_password',
    'delete_account': 'auth.delete_account',
    'forgot_password': 'auth.forgot_password',
    'reset_password': 'auth.reset_password',
    'send_invite_email': 'auth.send_invite_email',
    
    # Recipe blueprint routes
    'add_recipe': 'recipes.add_recipe',
    'view_recipe': 'recipes.view_recipe',
    'edit_recipe': 'recipes.edit_recipe',
    'delete_recipe': 'recipes.delete_recipe',
    'add_manual_ingredient': 'recipes.add_manual_ingredient',
    'extract_recipe_from_url': 'recipes.extract_recipe_from_url',
    
    # Grocery blueprint routes
    'update_grocery_list': 'grocery.update_grocery_list',
    'create_grocery_list': 'grocery.create_grocery_list',
    'switch_grocery_list': 'grocery.switch_grocery_list',
    'rename_grocery_list': 'grocery.rename_grocery_list',
    'delete_grocery_list': 'grocery.delete_grocery_list',
    'clear_grocery_list': 'grocery.clear_grocery_list',
    'shopping_mode': 'grocery.shopping_mode',
    'start_shopping': 'grocery.start_shopping',
    'end_shopping': 'grocery.end_shopping',
    'toggle_item': 'grocery.toggle_item',
    
    # Meal plan blueprint routes
    'meal_plan': 'meal_plan.meal_plan',
    'add_meal_plan_entry': 'meal_plan.add_meal_plan_entry',
    'update_meal_plan_entry': 'meal_plan.update_meal_plan_entry',
    'delete_meal_plan_entry': 'meal_plan.delete_meal_plan_entry',
    'add_meal_plan_to_list': 'meal_plan.add_meal_plan_to_list',
    'send_meal_plan_email': 'meal_plan.send_meal_plan_email',
    'find_similar_recipes': 'meal_plan.find_similar_recipes',
    'apply_similar_recipes': 'meal_plan.apply_similar_recipes',
    
    # Kroger blueprint routes
    'authenticate': 'kroger.authenticate',
    'callback': 'kroger.callback',
    'location_search': 'kroger.location_search',
    'select_store': 'kroger.select_store',
    'kroger_product_search': 'kroger.product_search',
    'item_choice': 'kroger.item_choice',
    'kroger_send_to_cart': 'kroger.send_to_cart',
    'skip_ingredient': 'kroger.skip_ingredient',
    
    # Admin blueprint routes
    'admin_dashboard': 'admin.admin_dashboard',
    'admin_login': 'admin.admin_login',
    'admin_delete_user': 'admin.admin_delete_user',
    'admin_delete_household': 'admin.admin_delete_household',
    'send_feature_announcement': 'admin.send_feature_announcement',
}

def update_file(filepath):
    """Update url_for calls in a single template file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    changes_made = []
    
    # Update each route mapping
    for old_route, new_route in ROUTE_MAPPING.items():
        # Pattern to match url_for('old_route') or url_for("old_route")
        # with optional parameters
        pattern = rf"url_for\(['\"]({old_route})['\"](.*?)\)"
        
        def replace_func(match):
            route_name = match.group(1)
            params = match.group(2)
            changes_made.append(f"{route_name} -> {new_route}")
            return f"url_for('{new_route}'{params})"
        
        content = re.sub(pattern, replace_func, content)
    
    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✅ Updated {filepath}")
        for change in set(changes_made):
            print(f"   - {change}")
        return True
    return False

# Update all template files
templates_dir = 'templates'
updated_count = 0

for filename in os.listdir(templates_dir):
    if filename.endswith('.html'):
        filepath = os.path.join(templates_dir, filename)
        if update_file(filepath):
            updated_count += 1

print(f"\n🎉 Updated {updated_count} template files!")

