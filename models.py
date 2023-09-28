import re
from fractions import Fraction
from collections import defaultdict
from flask import g
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy

bcrypt = Bcrypt()
db = SQLAlchemy()


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

    oath_token = db.Column(db.Text, nullable=True, unique=True)

    refresh_token = db.Column(db.Text, nullable=True, unique=True)

    profile_id = db.Column(db.Text, nullable=True, unique=True)

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
        """Find user with `username` and `password`.

        It searches for a user whose password hash matches this password
        and, if it finds such a user, returns that user object.

        If can't find matching user (or if password is wrong), returns False.
        """

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
    url = db.Column(db.Text, nullable=False)
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
    def parse_ingredients(cls, ingredients_text):
        """Parse ingredient text into individual objects"""

        ingredients = ingredients_text.split("\n")
        parsed_ingredients = []

        for ingredient in ingredients:
            print(f"Trying to match: {ingredient}")
            match = re.match(r"^(\S+)\s+(\S+)\s+(.*)", ingredient)
            print(f"Match result: {match}")
            if match:
                quantity, measurement, ingredient_name = match.groups()
                ingredient_name = ingredient_name[:40]
                print(ingredient_name)
                parsed_ingredients.append(
                    {
                        "quantity": quantity.strip() if quantity else None,
                        "measurement": measurement.strip() if measurement else None,
                        "ingredient_name": ingredient_name.strip(),
                    }
                )
        print(parsed_ingredients)
        return parsed_ingredients

    @classmethod
    def create_recipe(cls, ingredients_text, url, user_id, name, notes):
        """Takes parsed ingredients and creates a recipe object"""

        parsed_ingredients = cls.parse_ingredients(ingredients_text)

        recipe = cls(url=url, user_id=user_id, name=name, notes=notes)
        db.session.add(recipe)

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

        db.session.commit()
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


def connect_db(app):
    db.app = app
    db.init_app(app)
