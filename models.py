import re
import os
from fractions import Fraction
from collections import defaultdict
from flask import g
from flask_mail import Message
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI

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

    oath_token = db.Column(db.Text, nullable=True)

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
    source_type = db.Column(db.String(20), nullable=False, default='manual')
    url = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    recipe_ingredients = db.relationship("RecipeIngredient", back_populates="recipe")

    @staticmethod
    def is_float(value):
        """Ensure value is integer"""
        try:
            float(value)
            return True
        except ValueError:
            return False

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
5. Simplify ingredient descriptions by removing preparation methods:
   - "4 tbsp melted butter" → "4 tbsp butter"
   - "1 cup diced onions" → "1 cup onions"
   - "2 lbs ground beef" → "2 lb beef"
6. Format each ingredient as: "quantity measurement ingredient_name"
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
            print(f"=== OPENAI ERROR DEBUG ===")
            print(f"OpenAI API error: {e}")
            print(f"Error type: {type(e).__name__}")
            print("Falling back to original ingredients text")
            print(f"=== END OPENAI ERROR DEBUG ===")
            return ingredients_text

    @classmethod
    def parse_ingredients(cls, ingredients_text):
        """Parse ingredient text into individual objects"""

        # Ingredients should already be cleaned by OpenAI at this point
        ingredients = ingredients_text.split("\n")
        parsed_ingredients = []

        for ingredient in ingredients:
            # Clean up any remaining unwanted characters
            ingredient = re.sub(r'[▢☐□✓✔]', '', ingredient).strip()

            if not ingredient:
                continue

            print(f"Trying to match: {ingredient}")

            # Try different regex patterns
            patterns = [
                r"^(\d+(?:/\d+)?(?:\.\d+)?)\s+(\w+)\s+(.*)",  # "1/4 cup honey"
                r"^(\d+(?:/\d+)?(?:\.\d+)?)(\w+)\s+(.*)",     # "1/4cup honey"
                r"^(\d+(?:/\d+)?(?:\.\d+)?)(\w+)(.*)",        # "1/4cuphoney"
            ]

            match = None
            for pattern in patterns:
                match = re.match(pattern, ingredient)
                if match:
                    break

            print(f"Match result: {match}")
            if match:
                quantity, measurement, ingredient_name = match.groups()
                ingredient_name = ingredient_name.strip()[:40]
                parsed_ingredients.append({
                    "quantity": quantity.strip() if quantity else None,
                    "measurement": measurement.strip() if measurement else None,
                    "ingredient_name": ingredient_name.strip(),
                })
        return parsed_ingredients

    @classmethod
    def create_recipe(cls, ingredients_text, url, user_id, name, notes, source_type='manual'):
        """Takes parsed ingredients and creates a recipe object"""

        # Parse ingredients (already cleaned if from scraping)
        parsed_ingredients = cls.parse_ingredients(ingredients_text)

        recipe = cls(url=url, user_id=user_id, name=name, notes=notes, source_type=source_type)

        for ingredient_data in parsed_ingredients:
            quantity_string = ingredient_data["quantity"]
            if "/" in quantity_string:
                quantity = float(Fraction(quantity_string))
            elif cls.is_float(quantity_string):
                quantity = float(quantity_string)
            else:
                print(
                    f"Skipping ingredient: {ingredient_data['ingredient_name']} - Quantity is not a number."
                )
                continue

            recipe_ingredient = RecipeIngredient(
                quantity=quantity,
                measurement=ingredient_data["measurement"],
                ingredient_name=ingredient_data["ingredient_name"],
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
        combined_ingredients = defaultdict(lambda: [])

        for recipe in recipes:
            for recipe_ingredient in recipe.recipe_ingredients:
                ingredient_name = recipe_ingredient.ingredient_name
                quantity = recipe_ingredient.quantity
                measurement = recipe_ingredient.measurement

                found = False
                for entry in combined_ingredients[ingredient_name]:
                    if entry["measurement"] == measurement:
                        entry["quantity"] += quantity
                        found = True
                        break

                if not found:
                    combined_ingredients[ingredient_name].append(
                        {
                            "quantity": quantity,
                            "measurement": measurement,
                        }
                    )

        if grocery_list is not None:
            grocery_list.recipe_ingredients.clear()

        for ingredient_name, entries in combined_ingredients.items():
            for entry in entries:
                recipe_ingredient = RecipeIngredient(
                    ingredient_name=ingredient_name,
                    quantity=entry["quantity"],
                    measurement=entry["measurement"],
                )
                grocery_list.recipe_ingredients.append(recipe_ingredient)

        db.session.commit()

    @classmethod
    def send_email(cls, recipient, grocery_list, mail):
        """Send the grocery list via email."""
        msg = Message("Your Grocery List", recipients=[recipient])
        msg.body = f"Here is your list:\n{grocery_list.format_grocery_list()}"
        mail.send(msg)


    def format_grocery_list(self):
        """Format the grocery list for email."""
        ingredients_list = []
        for recipe_ingredient in self.recipe_ingredients:
            ingredient_detail = f"{recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}"
            ingredients_list.append(ingredient_detail)

        return "\n".join(ingredients_list)

def connect_db(app):
    db.app = app
    db.init_app(app)
