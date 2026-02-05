import re
import os
from collections import defaultdict
from datetime import datetime
from flask import g
from flask_mail import Message
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
from utils import parse_quantity_string, is_valid_float, get_est_now
from logging_config import logger

bcrypt = Bcrypt()
db = SQLAlchemy()

# Initialize OpenAI client using environment variable
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))


class Household(db.Model):
    """Household/family group for collaboration"""

    __tablename__ = "households"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    # Kroger integration - one account per household
    kroger_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    members = db.relationship("HouseholdMember", backref="household", cascade="all, delete-orphan")
    recipes = db.relationship("Recipe", backref="household", cascade="all, delete-orphan")
    grocery_lists = db.relationship("GroceryList", backref="household", cascade="all, delete-orphan")
    meal_plan_entries = db.relationship("MealPlanEntry", backref="household", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Household #{self.id}: {self.name}>"


class HouseholdMember(db.Model):
    """Association between users and households with roles"""

    __tablename__ = "household_members"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")  # 'owner' or 'member'
    joined_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    user = db.relationship("User", backref="household_memberships")

    def __repr__(self):
        return f"<HouseholdMember household_id={self.household_id} user_id={self.user_id} role={self.role}>"


class MealPlanEntry(db.Model):
    """Meal plan entry for a household"""

    __tablename__ = "meal_plan_entries"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=True)
    custom_meal_name = db.Column(db.String(200), nullable=True)  # For meals not in recipe box
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=True)  # 'breakfast', 'lunch', 'dinner', 'snack'
    assigned_cook_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    recipe = db.relationship("Recipe", backref="meal_plan_entries")
    assigned_cook = db.relationship("User", foreign_keys=[assigned_cook_user_id])

    @property
    def meal_name(self):
        """Get the meal name (either from recipe or custom)"""
        if self.recipe:
            return self.recipe.name
        return self.custom_meal_name or "Untitled Meal"

    @classmethod
    def send_meal_plan_email(cls, recipient, meal_entries, user_id, week_start, week_end, mail):
        """Send full meal plan summary plus detailed breakdown of user's assigned recipes."""
        from flask_mail import Message
        try:
            msg = Message(f"Meal Plan ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')})", recipients=[recipient])

            email_body = f"MEAL PLAN FOR THE WEEK\n"
            email_body += f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}\n"
            email_body += "="*70 + "\n\n"

            # SECTION 1: Full meal plan summary
            email_body += "FULL WEEK OVERVIEW\n"
            email_body += "="*70 + "\n\n"

            # Group all meals by date
            from collections import defaultdict
            all_meals_by_date = defaultdict(lambda: {'breakfast': [], 'lunch': [], 'dinner': []})
            for entry in meal_entries:
                if entry.meal_type in all_meals_by_date[entry.date]:
                    all_meals_by_date[entry.date][entry.meal_type].append(entry)

            # Display full week summary
            for date in sorted(all_meals_by_date.keys()):
                email_body += f"{date.strftime('%A, %B %d, %Y')}\n"
                email_body += "-"*70 + "\n"

                for meal_type in ['breakfast', 'lunch', 'dinner']:
                    entries = all_meals_by_date[date][meal_type]
                    if entries:
                        meal_type_display = meal_type.upper()
                        email_body += f"  {meal_type_display}:\n"
                        for entry in entries:
                            cook_name = entry.assigned_cook.username if entry.assigned_cook else "Unassigned"
                            email_body += f"    • {entry.meal_name} (Cook: {cook_name})\n"
                            if entry.notes:
                                email_body += f"      Notes: {entry.notes}\n"

                email_body += "\n"

            # SECTION 2: User's assigned meals with full details
            my_meals = [entry for entry in meal_entries if entry.assigned_cook_user_id == user_id]

            email_body += "\n" + "="*70 + "\n"
            email_body += "YOUR ASSIGNED RECIPES (DETAILED)\n"
            email_body += "="*70 + "\n\n"

            if not my_meals:
                email_body += "You have no meals assigned to you this week.\n"
                email_body += "Enjoy the break! 😊\n"
            else:
                email_body += f"You are cooking {len(my_meals)} meal(s) this week:\n\n"

                # Group user's meals by date
                my_meals_by_date = defaultdict(list)
                for entry in my_meals:
                    my_meals_by_date[entry.date].append(entry)

                # Display detailed breakdown
                for date in sorted(my_meals_by_date.keys()):
                    email_body += f"{date.strftime('%A, %B %d, %Y')}\n"
                    email_body += "-"*70 + "\n"

                    for entry in my_meals_by_date[date]:
                        meal_type_display = entry.meal_type.upper() if entry.meal_type else "MEAL"
                        email_body += f"\n{meal_type_display}: {entry.meal_name}\n"

                        if entry.notes:
                            email_body += f"Meal Notes: {entry.notes}\n"

                        # If it's a recipe with ingredients, include them
                        if entry.recipe:
                            if entry.recipe.url:
                                email_body += f"Recipe URL: {entry.recipe.url}\n"

                            if entry.recipe.recipe_ingredients:
                                email_body += "\nINGREDIENTS:\n"
                                for ingredient in entry.recipe.recipe_ingredients:
                                    # Skip default "1 unit" prefix - only show quantity if it's meaningful
                                    if (ingredient.quantity and
                                        ingredient.quantity > 0 and
                                        ingredient.measurement and
                                        not (ingredient.quantity == 1.0 and ingredient.measurement == "unit")):
                                        email_body += f"  • {ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}\n"
                                    else:
                                        email_body += f"  • {ingredient.ingredient_name}\n"

                            if entry.recipe.notes:
                                email_body += f"\nINSTRUCTIONS/NOTES:\n{entry.recipe.notes}\n"

                        email_body += "\n"

                email_body += "="*70 + "\n"
                email_body += "\nHappy cooking! 👨‍🍳👩‍🍳\n"

            msg.body = email_body
            mail.send(msg)

        except Exception as e:
            from logging_config import logger
            logger.error(f"Failed to send meal plan email: {e}", exc_info=True)
            raise e

    def __repr__(self):
        return f"<MealPlanEntry #{self.id}: {self.date} {self.meal_type}>"


class User(db.Model):
    """User in the system"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.Text, nullable=False, unique=True)

    username = db.Column(db.Text, nullable=False, unique=True)

    password = db.Column(db.Text, nullable=False)

    oauth_token = db.Column(db.Text, nullable=True)

    refresh_token = db.Column(db.Text, nullable=True, unique=True)

    profile_id = db.Column(db.Text, nullable=True)

    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    last_activity = db.Column(db.DateTime, nullable=True)

    recipes = db.relationship("Recipe", backref="user", cascade="all, delete-orphan")
    grocery_lists = db.relationship(
        "GroceryList",
        backref="user",
        cascade="all, delete-orphan",
        foreign_keys="GroceryList.user_id"
    )

    def __repr__(self):
        return f"<User #{self.id}: {self.username}, {self.email}>"

    def change_password(self, current_password, new_password, new_password_confirm):
        """Change password"""

        if not bcrypt.check_password_hash(self.password, current_password):
            raise ValueError("Current password is incorrect.")
        if new_password != new_password_confirm:
            raise ValueError("New passwords do not match.")
        self.password = bcrypt.generate_password_hash(new_password).decode("UTF-8")

    @classmethod
    def signup(cls, username, email, password):
        """Sign up user.

        Hashes password and adds user to system.
        """

        hashed_pwd = bcrypt.generate_password_hash(password).decode("UTF-8")

        user = User(username=username, email=email, password=hashed_pwd)

        db.session.add(user)
        return user

    @classmethod
    def authenticate(cls, username, password):
        """Find user with `username` and `password`."""

        user = cls.query.filter_by(username=username).first()

        if user:
            is_auth = bcrypt.check_password_hash(user.password, password)
            if is_auth:
                return user

        return False


class RecipeIngredient(db.Model):
    """Association object for recipes/ingredients"""

    __tablename__ = "recipes_ingredients"

    id = db.Column(db.Integer, primary_key=True)

    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"))

    ingredient_name = db.Column(db.String(40), nullable=False)

    quantity = db.Column(db.Float(40))

    measurement = db.Column(db.String(40))

    recipe = db.relationship("Recipe", back_populates="recipe_ingredients")


class Recipe(db.Model):
    """Recipe created by user"""

    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=True
    )
    name = db.Column(db.Text, nullable=False)
    url = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    visibility = db.Column(db.String(20), nullable=False, default="private")  # 'private' or 'household'
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    recipe_ingredients = db.relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")

    @classmethod
    def clean_ingredients_with_openai(cls, ingredients_text):
        """Clean and standardize scraped ingredients using OpenAI."""
        try:
            system_prompt = """You are a recipe ingredient parser. Clean and standardize the following scraped ingredients text according to these rules:

1. Separate concatenated words (e.g., "1/4cuphoney" → "1/4 cup honey")
2. Remove unwanted characters: checkboxes (▢☐□✓✔), bullet points, extra symbols
3. Standardize measurements:
   - "tb", "T", "tablespoon", "tablespoons" → "tbsp"
   - "c", "C", "cup", "cups" → "cup"
   - "t", "tsp", "teaspoon", "teaspoons" → "tsp"
   - "oz", "ounce", "ounces" → "oz"
   - "lb", "pound", "pounds" → "lb"
   - "g", "gram", "grams" → "g"
   - "kg", "kilogram", "kilograms" → "kg"
4. Convert decimal quantities to fractions where appropriate:
   - "0.25" → "1/4"
   - "0.5" → "1/2"
   - "0.75" → "3/4"
   - "0.33" → "1/3"
   - "0.67" → "2/3"
5. PRESERVE preparation modifiers and descriptive terms:
   - Keep: "diced", "chopped", "minced", "sliced", "fresh", "frozen", "dried", "ground", "whole", "crushed", "grated", etc.
   - "4 tbsp melted butter" → "4 tbsp melted butter"
   - "1 cup diced onions" → "1 cup diced onions"
   - "2 lbs ground beef" → "2 lb ground beef"
6. Format each ingredient as: "quantity measurement ingredient_name_with_modifiers"
7. Put each ingredient on a separate line
8. Remove empty lines

Return only the cleaned ingredients, one per line, with no additional text or explanations."""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Clean these ingredients:\n\n{ingredients_text}"}
                ],
                temperature=0.1,
                max_tokens=1000
            )

            cleaned_text = response.choices[0].message.content.strip()
            return cleaned_text

        except Exception as e:
            logger.error(f"OpenAI ingredient cleaning error: {e}", exc_info=True)
            logger.info("Falling back to original ingredients text")
            return ingredients_text

    @classmethod
    def parse_ingredients(cls, ingredients_text):
        """Parse ingredient text into individual objects using OpenAI"""

        try:
            system_prompt = """You are an ingredient parser. Parse each ingredient line into structured data with quantity, measurement, and ingredient name.

Return ONLY a JSON array where each ingredient is an object with these exact keys:
- "quantity": the numeric amount as a string (convert ranges like "3-4" to the first number "3")
- "measurement": the unit of measurement (cup, tbsp, tsp, lb, oz, etc.)
- "ingredient_name": the ingredient name including any descriptors

Examples:
"2 cups flour" → {"quantity": "2", "measurement": "cup", "ingredient_name": "flour"}
"1/4 tsp salt" → {"quantity": "1/4", "measurement": "tsp", "ingredient_name": "salt"}
"3-4 lb chicken" → {"quantity": "3", "measurement": "lb", "ingredient_name": "chicken"}
"salt and pepper to taste" → {"quantity": "1", "measurement": "unit", "ingredient_name": "salt and pepper to taste"}

Return only the JSON array, no explanations."""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse these ingredients:\n\n{ingredients_text}"}
                ],
                temperature=0.1,
                max_tokens=1000
            )

            import json
            parsed_ingredients = json.loads(response.choices[0].message.content.strip())
            return parsed_ingredients

        except Exception as e:
            logger.error(f"OpenAI ingredient parsing error: {e}", exc_info=True)
            logger.info("Falling back to simple parsing")

            # Fallback: simple parsing
            ingredients = ingredients_text.split("\n")
            parsed_ingredients = []
            for ingredient in ingredients:
                ingredient = ingredient.strip()
                if ingredient:
                    parsed_ingredients.append({
                        "quantity": "1",
                        "measurement": "unit",
                        "ingredient_name": ingredient[:40],
                    })
            return parsed_ingredients

    @classmethod
    def create_recipe(cls, ingredients_text, url, user_id, name, notes, household_id=None, visibility="private"):
        """Takes ingredients text and creates a recipe object"""

        recipe = cls(
            url=url,
            user_id=user_id,
            name=name,
            notes=notes,
            household_id=household_id,
            visibility=visibility
        )

        # Just split ingredients by lines and store them as-is
        ingredients = ingredients_text.split("\n")
        for ingredient in ingredients:
            ingredient = ingredient.strip()
            if ingredient:
                recipe_ingredient = RecipeIngredient(
                    quantity=1.0,  # Default quantity
                    measurement="unit",  # Default measurement
                    ingredient_name=ingredient[:40],  # Store the full ingredient text
                )
                recipe.recipe_ingredients.append(recipe_ingredient)

        return recipe


class GroceryListItem(db.Model):
    """Association object for grocery list items with metadata"""

    __tablename__ = "grocery_list_items"

    id = db.Column(db.Integer, primary_key=True)
    grocery_list_id = db.Column(db.Integer, db.ForeignKey("grocery_lists.id", ondelete="CASCADE"), nullable=False)
    recipe_ingredient_id = db.Column(db.Integer, db.ForeignKey("recipes_ingredients.id", ondelete="CASCADE"), nullable=False)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    added_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    recipe_ingredient = db.relationship("RecipeIngredient", backref="grocery_list_items")
    added_by = db.relationship("User", foreign_keys=[added_by_user_id])
    completed_by = db.relationship("User", foreign_keys=[completed_by_user_id])

    @property
    def is_checked(self):
        """Alias for completed field"""
        return self.completed

    @is_checked.setter
    def is_checked(self, value):
        """Alias setter for completed field"""
        self.completed = value

    def __repr__(self):
        return f"<GroceryListItem #{self.id} list={self.grocery_list_id} ingredient={self.recipe_ingredient_id}>"


class GroceryList(db.Model):
    """Grocery List of ingredients"""

    __tablename__ = "grocery_lists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=True
    )
    name = db.Column(db.Text, nullable=False, default="My Grocery List")
    status = db.Column(db.String(20), nullable=False, default="planning")  # 'planning', 'ready_to_shop', 'shopping', 'done'
    store = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)
    last_modified_at = db.Column(db.DateTime, nullable=False, default=get_est_now, onupdate=get_est_now)
    last_modified_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    shopping_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Who is currently shopping

    items = db.relationship("GroceryListItem", backref="grocery_list", cascade="all, delete-orphan")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    last_modified_by = db.relationship("User", foreign_keys=[last_modified_by_user_id])
    shopping_user = db.relationship("User", foreign_keys=[shopping_user_id])

    # Legacy support - keep recipe_ingredients relationship for backward compatibility
    @property
    def recipe_ingredients(self):
        """Legacy property to access ingredients through items"""
        return [item.recipe_ingredient for item in self.items]

    @classmethod
    def update_grocery_list(cls, selected_recipe_ids, grocery_list, user_id=None):
        """Create grocery list that includes chosen recipes"""

        recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()

        # Collect all ingredients from selected recipes
        all_ingredients = []
        for recipe in recipes:
            for recipe_ingredient in recipe.recipe_ingredients:
                all_ingredients.append({
                    'quantity': recipe_ingredient.quantity,
                    'measurement': recipe_ingredient.measurement,
                    'ingredient_name': recipe_ingredient.ingredient_name
                })

        # Use AI to consolidate similar ingredients
        consolidated_ingredients = cls.consolidate_ingredients_with_openai(all_ingredients)

        if grocery_list is not None:
            # Clear existing items
            for item in grocery_list.items:
                db.session.delete(item)

        # Create new recipe ingredients and grocery list items from consolidated list
        for ingredient_data in consolidated_ingredients:
            quantity_string = str(ingredient_data["quantity"])

            # Convert quantity to float using shared utility
            quantity = parse_quantity_string(quantity_string)
            if quantity is None:
                logger.warning(f"Skipping ingredient with invalid quantity: {ingredient_data['ingredient_name']}")
                continue

            recipe_ingredient = RecipeIngredient(
                ingredient_name=ingredient_data["ingredient_name"],
                quantity=quantity,
                measurement=ingredient_data["measurement"],
            )
            db.session.add(recipe_ingredient)
            db.session.flush()  # Get the ID

            # Create grocery list item
            grocery_list_item = GroceryListItem(
                grocery_list_id=grocery_list.id,
                recipe_ingredient_id=recipe_ingredient.id,
                added_by_user_id=user_id
            )
            db.session.add(grocery_list_item)

        # Update last modified metadata
        if user_id:
            grocery_list.last_modified_by_user_id = user_id
            grocery_list.last_modified_at = datetime.utcnow()

        db.session.commit()

    @classmethod
    def send_email(cls, recipient, grocery_list, selected_recipe_ids, mail):
        """Send the grocery list and selected recipes via email."""
        try:
            msg = Message("Your Grocery List & Recipes", recipients=[recipient])

            # Build email body with grocery list items (not recipe ingredients)
            email_body = "Here is your grocery list:\n\n"

            # Get all items from the grocery list
            for recipe_ingredient in grocery_list.recipe_ingredients:
                # Skip default "1 unit" prefix - only show quantity if it's meaningful
                if (recipe_ingredient.quantity and
                    recipe_ingredient.quantity > 0 and
                    recipe_ingredient.measurement and
                    not (recipe_ingredient.quantity == 1.0 and recipe_ingredient.measurement == "unit")):
                    email_body += f"• {recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}\n"
                else:
                    email_body += f"• {recipe_ingredient.ingredient_name}\n"

            # Add selected recipes if any
            if selected_recipe_ids:
                recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()
                if recipes:
                    email_body += "\n\n" + "="*50 + "\nSELECTED RECIPES\n" + "="*50 + "\n\n"

                    for recipe in recipes:
                        email_body += f"RECIPE: {recipe.name}\n"
                        if recipe.url:
                            email_body += f"URL: {recipe.url}\n"

                        email_body += "\nINGREDIENTS:\n"
                        for ingredient in recipe.recipe_ingredients:
                            # Skip default "1 unit" prefix - only show quantity if it's meaningful
                            if (ingredient.quantity and
                                ingredient.quantity > 0 and
                                ingredient.measurement and
                                not (ingredient.quantity == 1.0 and ingredient.measurement == "unit")):
                                email_body += f"• {ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}\n"
                            else:
                                email_body += f"• {ingredient.ingredient_name}\n"

                        if recipe.notes:
                            email_body += f"\nINSTRUCTIONS/NOTES:\n{recipe.notes}\n"

                        email_body += "\n" + "-"*30 + "\n\n"

            msg.body = email_body
            mail.send(msg)

        except Exception as e:
            logger.error(f"Failed to send grocery list email: {e}", exc_info=True)
            raise e

    @classmethod
    def send_recipes_only_email(cls, recipient, selected_recipe_ids, mail):
        """Send only the selected recipes via email."""
        try:
            msg = Message("Your Recipes", recipients=[recipient])

            if selected_recipe_ids:
                recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()
                if recipes:
                    email_body = "Here are your selected recipes:\n\n"

                    for recipe in recipes:
                        email_body += f"RECIPE: {recipe.name}\n"
                        if recipe.url:
                            email_body += f"URL: {recipe.url}\n"

                        email_body += "\nINGREDIENTS:\n"
                        for ingredient in recipe.recipe_ingredients:
                            # Skip default "1 unit" prefix - only show quantity if it's meaningful
                            if (ingredient.quantity and
                                ingredient.quantity > 0 and
                                ingredient.measurement and
                                not (ingredient.quantity == 1.0 and ingredient.measurement == "unit")):
                                email_body += f"• {ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}\n"
                            else:
                                email_body += f"• {ingredient.ingredient_name}\n"

                        if recipe.notes:
                            email_body += f"\nINSTRUCTIONS/NOTES:\n{recipe.notes}\n"

                        email_body += "\n" + "-"*30 + "\n\n"
                else:
                    email_body = "No recipes selected."
            else:
                email_body = "No recipes selected."

            msg.body = email_body
            mail.send(msg)

        except Exception as e:
            logger.error(f"Failed to send recipes email: {e}", exc_info=True)
            raise e

    def format_grocery_list(self):
        """Format the grocery list for email."""
        ingredients_list = []
        for recipe_ingredient in self.recipe_ingredients:
            ingredient_detail = f"{recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}"
            ingredients_list.append(ingredient_detail)

        return "\n".join(ingredients_list)

    @classmethod
    def consolidate_ingredients_with_openai(cls, ingredients_list):
        """Consolidate similar ingredients using OpenAI."""
        try:
            # Format ingredients for AI processing
            ingredients_text = "\n".join([
                f"{ing['quantity']} {ing['measurement']} {ing['ingredient_name']}"
                for ing in ingredients_list
            ])

            system_prompt = """You are an intelligent grocery list consolidator. Your task is to combine similar ingredients while preserving accurate quantities and important variety distinctions.

GROUPING RULES:

**Group together (same base ingredient):**
- Different preparation methods: "chopped onion", "diced onion", "sliced onion", "minced onion" → all become "onion"
- Generic vs specific: "tomatoes", "diced tomatoes" → both become "tomatoes"
- All butter types: "butter", "unsalted butter", "salted butter", "melted butter" → all become "butter"

**SKIP these ingredients (do not include in output):**
- Water in any form: "water", "cold water", "warm water", "boiling water"

**Keep separate (different varieties that matter for shopping):**
- Color/variety specifications: "yellow onion", "red onion", "white onion" → keep as separate items
- Different types: "roma tomatoes", "cherry tomatoes", "grape tomatoes" → keep separate
- Different cuts of meat: "chicken breast", "chicken thighs", "ground chicken" → keep separate
- Different dairy types: "whole milk", "2% milk", "skim milk" → keep separate
- Different cheese types: "cheddar cheese", "mozzarella cheese" → keep separate

**Quantity consolidation:**
- Add quantities together when combining ingredients
- Convert to simplest fraction form when possible
- Use the most common measurement unit when combining

**Output format:**
Return the consolidated list with one ingredient per line in format: "quantity measurement ingredient_name"
Use the simplest, most grocery-store-friendly name for each ingredient.
Only return the consolidated ingredients, no explanations."""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Consolidate these ingredients:\n\n{ingredients_text}"}
                ],
                temperature=0.1,
                max_tokens=1000
            )

            consolidated_text = response.choices[0].message.content.strip()

            # Parse the consolidated ingredients back into the expected format
            consolidated_ingredients = []
            for line in consolidated_text.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # Parse the consolidated ingredient - improved regex to handle mixed numbers and decimals
                # Matches: "2 cups flour", "1/2 cup sugar", "1.5 lb beef", "2 1/2 tbsp salt"
                match = re.match(r'^(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s+(\S+)\s+(.*)', line)
                if match:
                    quantity, measurement, ingredient_name = match.groups()
                    consolidated_ingredients.append({
                        'quantity': quantity.strip(),
                        'measurement': measurement.strip(),
                        'ingredient_name': ingredient_name.strip()
                    })
                else:
                    # Fallback: if parsing fails, keep the ingredient with default values
                    logger.warning(f"Could not parse consolidated ingredient: {line}")
                    consolidated_ingredients.append({
                        'quantity': '1',
                        'measurement': 'unit',
                        'ingredient_name': line
                    })

            return consolidated_ingredients

        except Exception as e:
            logger.error(f"OpenAI ingredient consolidation error: {e}", exc_info=True)
            logger.info("Falling back to original ingredients")
            return ingredients_list

def connect_db(app):
    db.app = app
    db.init_app(app)
