import re
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy

bcrypt = Bcrypt()
db = SQLAlchemy()


# Join table for Grocery List to Recipe
grocery_lists_ingredients = db.Table(
    "grocery_lists_ingredients",
    db.Column("grocery_list_id", db.Integer, db.ForeignKey("grocery_lists.id")),
    db.Column("ingredient_id", db.Integer, db.ForeignKey("ingredients.id")),
)


class User(db.Model):
    """User in the system"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.Text, nullable=False, unique=True)

    username = db.Column(db.Text, nullable=False, unique=True)

    password = db.Column(db.Text, nullable=False)

    oath_token = db.Column(db.Text, nullable=True, unique=True)

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

        user = User(
            username=username,
            email=email,
            password=hashed_pwd
        )

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
    __tablename__ = 'recipes_ingredients'
    
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), primary_key=True)
    
    quantity = db.Column(db.String(40)) 
    measurement = db.Column(db.String(40))
    
    ingredient = db.relationship("Ingredient", back_populates="recipe_ingredients")
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

    recipe_ingredients = db.relationship("RecipeIngredient", back_populates="recipe")

    
    @classmethod
    def parse_ingredients(cls, ingredients_text):
        """Parse ingredient text into individual objects"""

        ingredients = ingredients_text.split("\n")  # Split by lines
        parsed_ingredients = []

        for ingredient in ingredients:
            print(f"Trying to match: {ingredient}")
            match = re.match(r'^(\S+)\s+(\S+)\s+(.*)', ingredient)
            print(f"Match result: {match}")
            if match:
                quantity, measurement, ingredient_name = match.groups()
                print(ingredient_name)
                parsed_ingredients.append({
                    "quantity": quantity.strip() if quantity else None,
                    "measurement": measurement.strip() if measurement else None,
                    "ingredient": ingredient_name.strip(),
                })
        print(parsed_ingredients)
        return parsed_ingredients

    @classmethod
    def create_recipe(cls, ingredients_text, url, user_id, name):
        """Takes parsed ingredients and creates a recipe object"""

        parsed_ingredients = cls.parse_ingredients(ingredients_text)
        print(parsed_ingredients)
        recipe = cls(url=url, user_id=user_id, name=name)
        db.session.add(recipe)

        for ingredient_data in parsed_ingredients:
            ingredient = Ingredient(
                name=ingredient_data['ingredient']
            )
            recipe_ingredient = RecipeIngredient(
                quantity=ingredient_data['quantity'],
                measurement=ingredient_data['measurement'],
                ingredient=ingredient
            )
            recipe.recipe_ingredients.append(recipe_ingredient)

        db.session.commit()
        return recipe


class Ingredient(db.Model):
    """Ingredient in a recipe"""

    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(40), nullable=False)

    recipe_ingredients = db.relationship("RecipeIngredient", back_populates="ingredient")


class GroceryList(db.Model):
    __tablename__ = "grocery_lists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    ingredients = db.relationship("Ingredient", secondary=grocery_lists_ingredients, backref="grocery_lists")

    def add_recipe_to_grocery_list(recipe, grocery_list):
        """Insert ingredients into a grocery list"""
        for recipe_ingredient in recipe.recipe_ingredients:
            ingredient = recipe_ingredient.ingredient
            grocery_list.ingredients.append(ingredient)
        db.session.commit()



def connect_db(app):
    db.app = app
    db.init_app(app)
