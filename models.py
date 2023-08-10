from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy

bcrypt = Bcrypt()
db = SQLAlchemy()


# Join table for Recipe to Ingredient
recipes_ingredients = db.Table(
    "recipes_ingredients",
    db.Column("recipe_id", db.Integer, db.ForeignKey("recipes.id")),
    db.Column("ingredient_id", db.Integer, db.ForeignKey("ingredients.id")),
)

# Join table for Grocery List to Recipe
grocery_lists_recipes = db.Table(
    "grocery_lists_recipes",
    db.Column("grocery_list_id", db.Integer, db.ForeignKey("grocery_lists.id")),
    db.Column("recipe_id", db.Integer, db.ForeignKey("recipes.id")),
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


class Recipe(db.Model):
    """Recipe created by user"""

    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    ingredient = db.Column(db.Text, nullable=False)

    url = db.Column(db.Text, nullable=False)

    ingredients = db.relationship(
        "Ingredient", secondary=recipes_ingredients, backref="recipes"
    )

    
    @classmethod
    def parse_ingredients(cls, ingredients_text):
        """Parse ingredient text into individual objects"""

        ingredients = ingredients_text.split("\n")  # Split by lines
        parsed_ingredients = []

        for ingredient in ingredients:
            match = re.match(r'^▢([\d\s/]+)?\s*([a-zA-Z]*)?\s*(.*)', ingredient)
            if match:
                quantity, measurement, ingredient_name = match.groups()
                parsed_ingredients.append({
                    "quantity": quantity.strip() if quantity else None,
                    "measurement": measurement.strip() if measurement else None,
                    "ingredient": ingredient_name.strip(),
                })

        return parsed_ingredients

    @classmethod
    def create_recipe(cls, ingredients_text, url):
        parsed_ingredients = cls.parse_ingredients(ingredients_text)
        recipe = cls(url=url)
        db.session.add(recipe)

        for ingredient_data in parsed_ingredients:
            ingredient = Ingredient(
                name=ingredient_data['ingredient']
            )
            recipe.ingredients.append(ingredient)

        db.session.commit()
        return recipe


class Ingredient(db.Model):
    """Ingredient in a recipe"""

    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(40), nullable=False)


class GroceryList(db.Model):
    """Grocery List of ingreedients"""

    __tablename__ = "grocery_lists"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    recipes = db.relationship(
        "Recipe", secondary=grocery_lists_recipes, backref="grocery_lists"
    )


def connect_db(app):
    db.app = app
    db.init_app(app)
