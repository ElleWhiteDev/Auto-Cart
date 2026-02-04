import re
import os
from collections import defaultdict
from flask import g
from flask_mail import Message
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
from utils import parse_quantity_string, is_valid_float
from logging_config import logger

bcrypt = Bcrypt()
db = SQLAlchemy()

# Initialize OpenAI client using environment variable
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))


# Join table for Grocery List to Recipe Ingredient
grocery_lists_recipe_ingredients = db.Table(
    "grocery_lists_recipe_ingredients",
    db.Column("grocery_list_id", db.Integer, db.ForeignKey("grocery_lists.id")),
    db.Column(
        "recipe_ingredient_id", db.Integer, db.ForeignKey("recipes_ingredients.id")
    ),
)


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

    recipes = db.relationship("Recipe", backref="user", cascade="all, delete-orphan")
    grocery_lists = db.relationship(
        "GroceryList", backref="user", cascade="all, delete-orphan"
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
    name = db.Column(db.Text, nullable=False)
    url = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    recipe_ingredients = db.relationship("RecipeIngredient", back_populates="recipe")

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
    def create_recipe(cls, ingredients_text, url, user_id, name, notes):
        """Takes ingredients text and creates a recipe object"""

        recipe = cls(url=url, user_id=user_id, name=name, notes=notes)

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


class GroceryList(db.Model):
    """Grocery List of ingredients"""

    __tablename__ = "grocery_lists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    recipe_ingredients = db.relationship(
        "RecipeIngredient",
        secondary=grocery_lists_recipe_ingredients,
        backref="grocery_lists",
    )

    @classmethod
    def update_grocery_list(cls, selected_recipe_ids, grocery_list):
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
            grocery_list.recipe_ingredients.clear()

        # Create new recipe ingredients from consolidated list
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
            grocery_list.recipe_ingredients.append(recipe_ingredient)

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
