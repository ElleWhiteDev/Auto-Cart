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
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


class Household(db.Model):
    """Household/family group for collaboration.

    A household can have multiple owners and members. Profiles (users) can belong to
    multiple households - they can be owners of some and members of others.
    All recipes and grocery lists are scoped to households.
    """

    __tablename__ = "households"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    # Kroger integration - one account per household
    kroger_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    members = db.relationship(
        "HouseholdMember", backref="household", cascade="all, delete-orphan"
    )
    recipes = db.relationship(
        "Recipe", backref="household", cascade="all, delete-orphan"
    )
    grocery_lists = db.relationship(
        "GroceryList", backref="household", cascade="all, delete-orphan"
    )
    meal_plan_entries = db.relationship(
        "MealPlanEntry", backref="household", cascade="all, delete-orphan"
    )

    def get_owners(self):
        """Get all owner members of this household"""
        return [m for m in self.members if m.is_owner()]

    def get_regular_members(self):
        """Get all non-owner members of this household"""
        return [m for m in self.members if not m.is_owner()]

    def is_user_owner(self, user_id):
        """Check if a user is an owner of this household"""
        membership = HouseholdMember.query.filter_by(
            household_id=self.id, user_id=user_id
        ).first()
        return membership and membership.is_owner()

    def is_user_member(self, user_id):
        """Check if a user is a member (owner or regular) of this household"""
        membership = HouseholdMember.query.filter_by(
            household_id=self.id, user_id=user_id
        ).first()
        return membership is not None

    def get_connected_households(self):
        """Get all households that share at least one member with this household.

        Returns households that have overlapping membership - useful for finding
        households where recipes can be shared by owners.
        """
        # Get all member user IDs from this household
        member_user_ids = [m.user_id for m in self.members]

        if not member_user_ids:
            return []

        # Find all households that have any of these users as members
        connected_households = db.session.query(Household).join(
            HouseholdMember
        ).filter(
            HouseholdMember.user_id.in_(member_user_ids),
            Household.id != self.id  # Exclude this household itself
        ).distinct().all()

        return connected_households

    def __repr__(self):
        return f"<Household #{self.id}: {self.name}>"


class HouseholdMember(db.Model):
    """Association between users and households with roles.

    A user can be a member of multiple households with different roles.
    Roles: 'owner' - can manage household settings and members
           'member' - regular household member
    """

    __tablename__ = "household_members"
    __table_args__ = (
        db.UniqueConstraint("household_id", "user_id", name="unique_household_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role = db.Column(
        db.String(20), nullable=False, default="member"
    )  # 'owner' or 'member'
    joined_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    user = db.relationship("User", backref="household_memberships")

    def is_owner(self):
        """Check if this membership has owner privileges"""
        return self.role == "owner"

    def is_member(self):
        """Check if this is a regular member (not owner)"""
        return self.role == "member"

    def __repr__(self):
        return f"<HouseholdMember household_id={self.household_id} user_id={self.user_id} role={self.role}>"


# Association table for meal plan entries and assigned cooks (many-to-many)
meal_plan_cooks = db.Table(
    "meal_plan_cooks",
    db.Column(
        "meal_plan_entry_id",
        db.Integer,
        db.ForeignKey("meal_plan_entries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "user_id",
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class MealPlanEntry(db.Model):
    """Meal plan entry for a household"""

    __tablename__ = "meal_plan_entries"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id = db.Column(
        db.Integer, db.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=True
    )
    custom_meal_name = db.Column(
        db.String(200), nullable=True
    )  # For meals not in recipe box
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(
        db.String(20), nullable=True
    )  # 'breakfast', 'lunch', 'dinner', 'snack'
    assigned_cook_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )  # Legacy single cook field - kept for backward compatibility
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    recipe = db.relationship("Recipe", backref="meal_plan_entries")
    assigned_cook = db.relationship(
        "User", foreign_keys=[assigned_cook_user_id]
    )  # Legacy single cook
    assigned_cooks = db.relationship(
        "User",
        secondary=meal_plan_cooks,
        backref="assigned_meals",
        lazy="dynamic",
    )  # New multi-cook support

    @property
    def meal_name(self):
        """Get the meal name (either from recipe or custom)"""
        if self.recipe:
            return self.recipe.name
        return self.custom_meal_name or "Untitled Meal"

    @classmethod
    def send_meal_plan_email(
        cls, recipient, meal_entries, user_id, week_start, week_end, mail
    ):
        """Send full meal plan summary plus detailed breakdown of user's assigned recipes."""
        from flask_mail import Message
        from collections import defaultdict
        from flask import current_app

        try:
            # Get response email from config
            response_email = current_app.config.get(
                "MAIL_DEFAULT_SENDER", "support@autocart.com"
            )
            # Group all meals by date
            all_meals_by_date = defaultdict(
                lambda: {"breakfast": [], "lunch": [], "dinner": []}
            )
            for entry in meal_entries:
                if entry.meal_type in all_meals_by_date[entry.date]:
                    all_meals_by_date[entry.date][entry.meal_type].append(entry)

            # Get user's assigned meals
            my_meals = [
                entry
                for entry in meal_entries
                if entry.assigned_cook_user_id == user_id
            ]
            my_meals_by_date = defaultdict(list)
            for entry in my_meals:
                my_meals_by_date[entry.date].append(entry)

            # Build HTML email
            html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #004c91 0%, #1e6bb8 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .logo {{ width: 50px; height: 50px; margin-bottom: 10px; }}
        .content {{ background-color: #f9f9f9; padding: 30px; border: 1px solid #ddd; border-top: none; }}
        .week-overview {{ background-color: white; padding: 20px; margin: 20px 0; border-left: 4px solid #004c91; border-radius: 5px; }}
        .day-section {{ margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #eee; }}
        .day-section:last-child {{ border-bottom: none; }}
        .day-title {{ color: #004c91; font-weight: bold; margin-bottom: 10px; }}
        .meal-item {{ margin-left: 15px; padding: 5px 0; }}
        .meal-type {{ color: #ff6600; font-weight: bold; }}
        .cook-name {{ color: #666; font-size: 0.9em; }}
        .my-recipes {{ background-color: white; padding: 20px; margin: 20px 0; border-left: 4px solid #ff6600; border-radius: 5px; }}
        .recipe-card {{ background-color: #f0f8ff; padding: 15px; margin: 15px 0; border-radius: 5px; }}
        .recipe-title {{ color: #004c91; margin-top: 0; }}
        .recipe-url {{ color: #ff6600; text-decoration: none; word-break: break-all; }}
        .recipe-url:hover {{ text-decoration: underline; }}
        .ingredient-list {{ list-style: none; padding-left: 0; }}
        .ingredient-list li {{ padding: 5px 0; border-bottom: 1px solid #ddd; }}
        .ingredient-list li:last-child {{ border-bottom: none; }}
        .notes {{ background-color: #fff9e6; padding: 10px; border-radius: 5px; margin-top: 10px; font-style: italic; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; border-radius: 0 0 5px 5px; background-color: #f9f9f9; border: 1px solid #ddd; border-top: none; }}
        .no-meals {{ text-align: center; padding: 20px; color: #999; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="logo">
                <circle cx="50" cy="50" r="48" fill="#FF8C42"/>
                <g transform="translate(50, 52)">
                    <path d="M -26 -20 L -20 8 L 20 8 L 24 -20 Z" fill="#007bff" stroke="#004c91" stroke-width="2.5"/>
                    <path d="M -28 -20 L -32 -32 L -20 -32" fill="none" stroke="#007bff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <circle cx="-10" cy="16" r="5" fill="#004c91"/>
                    <circle cx="10" cy="16" r="5" fill="#004c91"/>
                    <line x1="-16" y1="-14" x2="-16" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="-5" y1="-14" x2="-5" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="6" y1="-14" x2="6" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="16" y1="-14" x2="16" y2="5" stroke="white" stroke-width="2"/>
                </g>
            </svg>
            <h1 style="margin: 10px 0 0 0; font-size: 24px;">Meal Plan</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px;">{week_start.strftime("%B %d")} - {week_end.strftime("%B %d, %Y")}</p>
        </div>
        <div class="content">
            <div class="week-overview">
                <h2 style="color: #004c91; margin-top: 0;">📅 Full Week Overview</h2>
"""

            # Add week overview
            for date in sorted(all_meals_by_date.keys()):
                html_body += f"""                <div class="day-section">
                    <div class="day-title">{date.strftime("%A, %B %d, %Y")}</div>
"""
                for meal_type in ["breakfast", "lunch", "dinner"]:
                    entries = all_meals_by_date[date][meal_type]
                    if entries:
                        meal_type_display = meal_type.capitalize()
                        html_body += f"""                    <div class="meal-item">
                        <span class="meal-type">{meal_type_display}:</span><br>
"""
                        for entry in entries:
                            cook_name = (
                                entry.assigned_cook.username
                                if entry.assigned_cook
                                else "Unassigned"
                            )
                            html_body += f"""                        • {entry.meal_name} <span class="cook-name">(Cook: {cook_name})</span><br>
"""
                            if entry.notes:
                                html_body += f"""                        <span style="font-size: 0.9em; color: #666;">Notes: {entry.notes}</span><br>
"""
                        html_body += """                    </div>
"""
                html_body += """                </div>
"""

            html_body += """            </div>

            <div class="my-recipes">
                <h2 style="color: #ff6600; margin-top: 0;">👨‍🍳 Your Assigned Recipes</h2>
"""

            if not my_meals:
                html_body += """                <div class="no-meals">
                    <p>You have no meals assigned to you this week.</p>
                    <p>Enjoy the break! 😊</p>
                </div>
"""
            else:
                html_body += f"""                <p>You are cooking <strong>{len(my_meals)} meal(s)</strong> this week:</p>
"""
                for date in sorted(my_meals_by_date.keys()):
                    for entry in my_meals_by_date[date]:
                        meal_type_display = (
                            entry.meal_type.capitalize() if entry.meal_type else "Meal"
                        )
                        html_body += f"""                <div class="recipe-card">
                    <h3 class="recipe-title">{date.strftime("%A, %B %d")} - {meal_type_display}: {entry.meal_name}</h3>
"""
                        if entry.notes:
                            html_body += f"""                    <div class="notes">Meal Notes: {entry.notes}</div>
"""

                        if entry.recipe:
                            if entry.recipe.url:
                                html_body += f"""                    <p><strong>Recipe URL:</strong> <a href="{entry.recipe.url}" class="recipe-url">{entry.recipe.url}</a></p>
"""

                            if entry.recipe.recipe_ingredients:
                                html_body += """                    <h4 style="color: #ff6600; margin-top: 15px;">Ingredients:</h4>
                    <ul class="ingredient-list">
"""
                                for ingredient in entry.recipe.recipe_ingredients:
                                    if (
                                        ingredient.quantity
                                        and ingredient.quantity > 0
                                        and ingredient.measurement
                                        and not (
                                            ingredient.quantity == 1.0
                                            and ingredient.measurement == "unit"
                                        )
                                    ):
                                        html_body += f"""                        <li>{ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}</li>
"""
                                    else:
                                        html_body += f"""                        <li>{ingredient.ingredient_name}</li>
"""
                                html_body += """                    </ul>
"""

                            if entry.recipe.notes:
                                html_body += f"""                    <div class="notes">
                        <strong>Instructions/Notes:</strong><br>
                        {entry.recipe.notes.replace(chr(10), "<br>")}
                    </div>
"""
                        html_body += """                </div>
"""

                html_body += """                <p style="text-align: center; margin-top: 20px; font-size: 1.1em;">Happy cooking! 👨‍🍳👩‍🍳</p>
"""

            html_body += f"""            </div>
        </div>
        <div class="footer">
            <p>Auto-Cart - Smart Household Grocery Management</p>
            <p style="margin-top: 10px; font-size: 11px;">Questions? Reply to <a href="mailto:{response_email}" style="color: #999;">{response_email}</a></p>
        </div>
    </div>
</body>
</html>
"""

            # Build plain text version
            text_body = f"MEAL PLAN FOR THE WEEK\n"
            text_body += (
                f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}\n"
            )
            text_body += "=" * 70 + "\n\n"
            text_body += "FULL WEEK OVERVIEW\n"
            text_body += "=" * 70 + "\n\n"

            for date in sorted(all_meals_by_date.keys()):
                text_body += f"{date.strftime('%A, %B %d, %Y')}\n"
                text_body += "-" * 70 + "\n"

                for meal_type in ["breakfast", "lunch", "dinner"]:
                    entries = all_meals_by_date[date][meal_type]
                    if entries:
                        meal_type_display = meal_type.upper()
                        text_body += f"  {meal_type_display}:\n"
                        for entry in entries:
                            cook_name = (
                                entry.assigned_cook.username
                                if entry.assigned_cook
                                else "Unassigned"
                            )
                            text_body += (
                                f"    • {entry.meal_name} (Cook: {cook_name})\n"
                            )
                            if entry.notes:
                                text_body += f"      Notes: {entry.notes}\n"

                text_body += "\n"

            text_body += "\n" + "=" * 70 + "\n"
            text_body += "YOUR ASSIGNED RECIPES (DETAILED)\n"
            text_body += "=" * 70 + "\n\n"

            if not my_meals:
                text_body += "You have no meals assigned to you this week.\n"
                text_body += "Enjoy the break! 😊\n"
            else:
                text_body += f"You are cooking {len(my_meals)} meal(s) this week:\n\n"

                for date in sorted(my_meals_by_date.keys()):
                    text_body += f"{date.strftime('%A, %B %d, %Y')}\n"
                    text_body += "-" * 70 + "\n"

                    for entry in my_meals_by_date[date]:
                        meal_type_display = (
                            entry.meal_type.upper() if entry.meal_type else "MEAL"
                        )
                        text_body += f"\n{meal_type_display}: {entry.meal_name}\n"

                        if entry.notes:
                            text_body += f"Meal Notes: {entry.notes}\n"

                        if entry.recipe:
                            if entry.recipe.url:
                                text_body += f"Recipe URL: {entry.recipe.url}\n"

                            if entry.recipe.recipe_ingredients:
                                text_body += "\nINGREDIENTS:\n"
                                for ingredient in entry.recipe.recipe_ingredients:
                                    if (
                                        ingredient.quantity
                                        and ingredient.quantity > 0
                                        and ingredient.measurement
                                        and not (
                                            ingredient.quantity == 1.0
                                            and ingredient.measurement == "unit"
                                        )
                                    ):
                                        text_body += f"  • {ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}\n"
                                    else:
                                        text_body += (
                                            f"  • {ingredient.ingredient_name}\n"
                                        )

                            if entry.recipe.notes:
                                text_body += (
                                    f"\nINSTRUCTIONS/NOTES:\n{entry.recipe.notes}\n"
                                )

                        text_body += "\n"

                text_body += "=" * 70 + "\n"
                text_body += "\nHappy cooking! 👨‍🍳👩‍🍳\n"

            text_body += f"\n---\nAuto-Cart - Smart Household Grocery Management\n\nQuestions? Reply to {response_email}"

            msg = Message(
                f"Meal Plan ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')})",
                recipients=[recipient],
                body=text_body,
                html=html_body,
            )
            mail.send(msg)

        except Exception as e:
            from logging_config import logger

            logger.error(f"Failed to send meal plan email: {e}", exc_info=True)
            raise e

    def __repr__(self):
        return f"<MealPlanEntry #{self.id}: {self.date} {self.meal_type}>"


class User(db.Model):
    """User/Profile in the system.

    A user (profile) can be part of multiple households - as owner of some and member of others.
    The profile_id field is used for Kroger API integration.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.Text, nullable=False, unique=True)

    username = db.Column(db.Text, nullable=False, unique=True)

    password = db.Column(db.Text, nullable=False)

    oauth_token = db.Column(db.Text, nullable=True)

    refresh_token = db.Column(db.Text, nullable=True, unique=True)

    profile_id = db.Column(db.Text, nullable=True)  # Kroger profile ID

    alexa_access_token = db.Column(
        db.Text, nullable=True, unique=True
    )  # OAuth token for Alexa integration

    # Optional default grocery list Alexa should use for this user
    alexa_default_grocery_list_id = db.Column(
        db.Integer,
        db.ForeignKey("grocery_lists.id", ondelete="SET NULL"),
        nullable=True,
    )

    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    last_activity = db.Column(db.DateTime, nullable=True)

    recipes = db.relationship("Recipe", backref="user", cascade="all, delete-orphan")
    grocery_lists = db.relationship(
        "GroceryList",
        backref="user",
        cascade="all, delete-orphan",
        foreign_keys="GroceryList.user_id",
    )

    # Direct relationship to the user's Alexa default grocery list (if configured)
    alexa_default_grocery_list = db.relationship(
        "GroceryList", foreign_keys=[alexa_default_grocery_list_id]
    )

    def get_households(self):
        """Get all households this user is a member of"""
        return [m.household for m in self.household_memberships]

    def get_owned_households(self):
        """Get all households this user owns"""
        return [m.household for m in self.household_memberships if m.is_owner()]

    def get_member_households(self):
        """Get all households where this user is a regular member (not owner)"""
        return [m.household for m in self.household_memberships if m.is_member()]

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
    """Recipe created by user and scoped to a household.

    Recipes are always associated with a household. When a user creates a recipe,
    it belongs to their currently active household. Users can access recipes from
    all households they are members of.
    """

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
    visibility = db.Column(
        db.String(20), nullable=False, default="private"
    )  # 'private' or 'household'
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    recipe_ingredients = db.relationship(
        "RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan"
    )

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
                    {
                        "role": "user",
                        "content": f"Clean these ingredients:\n\n{ingredients_text}",
                    },
                ],
                temperature=0.1,
                max_tokens=1000,
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
- "quantity": the numeric amount as a string (convert ranges like "3-4" to the first number "3"). If no quantity is specified, use "1".
- "measurement": the unit of measurement (cup, tbsp, tsp, lb, oz, etc.). If no measurement is specified, use "unit".
- "ingredient_name": the ingredient name including any descriptors

Examples:
"2 cups flour" → {"quantity": "2", "measurement": "cup", "ingredient_name": "flour"}
"1/4 tsp salt" → {"quantity": "1/4", "measurement": "tsp", "ingredient_name": "salt"}
"3-4 lb chicken" → {"quantity": "3", "measurement": "lb", "ingredient_name": "chicken"}
"milk" → {"quantity": "1", "measurement": "unit", "ingredient_name": "milk"}
"salt and pepper to taste" → {"quantity": "1", "measurement": "unit", "ingredient_name": "salt and pepper to taste"}

Return only the JSON array, no explanations."""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Parse these ingredients:\n\n{ingredients_text}",
                    },
                ],
                temperature=0.1,
                max_tokens=1000,
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
                    parsed_ingredients.append(
                        {
                            "quantity": "1",
                            "measurement": "unit",
                            "ingredient_name": ingredient[:40],
                        }
                    )
            return parsed_ingredients

    @classmethod
    def create_recipe(
        cls,
        ingredients_text,
        url,
        user_id,
        name,
        notes,
        household_id=None,
        visibility="private",
    ):
        """Takes ingredients text and creates a recipe object"""

        recipe = cls(
            url=url,
            user_id=user_id,
            name=name,
            notes=notes,
            household_id=household_id,
            visibility=visibility,
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
    grocery_list_id = db.Column(
        db.Integer,
        db.ForeignKey("grocery_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipe_ingredient_id = db.Column(
        db.Integer,
        db.ForeignKey("recipes_ingredients.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at = db.Column(db.DateTime, nullable=True)
    added_at = db.Column(db.DateTime, nullable=False, default=get_est_now)

    recipe_ingredient = db.relationship(
        "RecipeIngredient", backref="grocery_list_items"
    )
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
    """Grocery List of ingredients scoped to a household.

    Grocery lists belong to a household and can be collaboratively managed by all
    household members. Users can access grocery lists from all households they belong to.
    """

    __tablename__ = "grocery_lists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=True
    )
    name = db.Column(db.Text, nullable=False, default="My Grocery List")
    status = db.Column(
        db.String(20), nullable=False, default="planning"
    )  # 'planning', 'ready_to_shop', 'shopping', 'done'
    store = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=get_est_now)
    last_modified_at = db.Column(
        db.DateTime, nullable=False, default=get_est_now, onupdate=get_est_now
    )
    last_modified_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    shopping_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )  # Who is currently shopping

    items = db.relationship(
        "GroceryListItem", backref="grocery_list", cascade="all, delete-orphan"
    )
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
        """Add selected recipes to current grocery list (append, not replace)"""

        recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()

        # Collect all ingredients - START WITH EXISTING ONES from the grocery list
        all_ingredients = []

        # Add existing ingredients from the grocery list
        if grocery_list is not None:
            for existing_item in grocery_list.items:
                ingredient = existing_item.recipe_ingredient
                all_ingredients.append(
                    {
                        "quantity": ingredient.quantity,
                        "measurement": ingredient.measurement,
                        "ingredient_name": ingredient.ingredient_name,
                    }
                )

        # Add new ingredients from selected recipes
        for recipe in recipes:
            for recipe_ingredient in recipe.recipe_ingredients:
                all_ingredients.append(
                    {
                        "quantity": recipe_ingredient.quantity,
                        "measurement": recipe_ingredient.measurement,
                        "ingredient_name": recipe_ingredient.ingredient_name,
                    }
                )

        # Use AI to consolidate similar ingredients (will merge duplicates)
        consolidated_ingredients = cls.consolidate_ingredients_with_openai(
            all_ingredients
        )

        if grocery_list is not None:
            # NOW clear and rebuild with consolidated list (which includes both old and new)
            for item in grocery_list.items:
                db.session.delete(item)

        # Create new recipe ingredients and grocery list items from consolidated list
        for ingredient_data in consolidated_ingredients:
            quantity_string = str(ingredient_data["quantity"])

            # Convert quantity to float using shared utility
            quantity = parse_quantity_string(quantity_string)
            if quantity is None:
                logger.warning(
                    f"Skipping ingredient with invalid quantity: {ingredient_data['ingredient_name']}"
                )
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
                added_by_user_id=user_id,
            )
            db.session.add(grocery_list_item)

        # Update last modified metadata
        if user_id:
            grocery_list.last_modified_by_user_id = user_id
            grocery_list.last_modified_at = get_est_now()

        db.session.commit()

    @classmethod
    def send_email(cls, recipient, grocery_list, selected_recipe_ids, mail):
        """Send the grocery list and selected recipes via email."""
        try:
            # Build HTML email body
            html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #004c91 0%, #1e6bb8 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .logo {{ width: 50px; height: 50px; margin-bottom: 10px; }}
        .content {{ background-color: #f9f9f9; padding: 30px; border: 1px solid #ddd; border-top: none; }}
        .grocery-section {{ background-color: white; padding: 20px; margin: 20px 0; border-left: 4px solid #004c91; border-radius: 5px; }}
        .recipe-section {{ background-color: white; padding: 20px; margin: 20px 0; border-left: 4px solid #ff6600; border-radius: 5px; }}
        .ingredient-list {{ list-style: none; padding-left: 0; }}
        .ingredient-list li {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
        .ingredient-list li:last-child {{ border-bottom: none; }}
        .recipe-title {{ color: #004c91; margin-top: 0; }}
        .recipe-url {{ color: #ff6600; text-decoration: none; word-break: break-all; }}
        .recipe-url:hover {{ text-decoration: underline; }}
        .notes {{ background-color: #f0f8ff; padding: 15px; border-radius: 5px; margin-top: 15px; font-style: italic; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; border-radius: 0 0 5px 5px; background-color: #f9f9f9; border: 1px solid #ddd; border-top: none; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="logo">
                <circle cx="50" cy="50" r="48" fill="#FF8C42"/>
                <g transform="translate(50, 52)">
                    <path d="M -26 -20 L -20 8 L 20 8 L 24 -20 Z" fill="#007bff" stroke="#004c91" stroke-width="2.5"/>
                    <path d="M -28 -20 L -32 -32 L -20 -32" fill="none" stroke="#007bff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <circle cx="-10" cy="16" r="5" fill="#004c91"/>
                    <circle cx="10" cy="16" r="5" fill="#004c91"/>
                    <line x1="-16" y1="-14" x2="-16" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="-5" y1="-14" x2="-5" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="6" y1="-14" x2="6" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="16" y1="-14" x2="16" y2="5" stroke="white" stroke-width="2"/>
                </g>
            </svg>
            <h1 style="margin: 10px 0 0 0; font-size: 24px;">Your Grocery List & Recipes</h1>
        </div>
        <div class="content">
            <div class="grocery-section">
                <h2 style="color: #004c91; margin-top: 0;">🛒 Grocery List: {grocery_list.name}</h2>
                <ul class="ingredient-list">
"""

            # Add grocery list items
            for recipe_ingredient in grocery_list.recipe_ingredients:
                if (
                    recipe_ingredient.quantity
                    and recipe_ingredient.quantity > 0
                    and recipe_ingredient.measurement
                    and not (
                        recipe_ingredient.quantity == 1.0
                        and recipe_ingredient.measurement == "unit"
                    )
                ):
                    html_body += f"                    <li>✓ {recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}</li>\n"
                else:
                    html_body += f"                    <li>✓ {recipe_ingredient.ingredient_name}</li>\n"

            html_body += """                </ul>
            </div>
"""

            # Add selected recipes if any
            if selected_recipe_ids:
                recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()
                if recipes:
                    for recipe in recipes:
                        html_body += f"""            <div class="recipe-section">
                <h3 class="recipe-title">📖 {recipe.name}</h3>
"""
                        if recipe.url:
                            html_body += f"""                <p><strong>Recipe URL:</strong> <a href="{recipe.url}" class="recipe-url">{recipe.url}</a></p>
"""

                        html_body += """                <h4 style="color: #ff6600; margin-top: 20px;">Ingredients:</h4>
                <ul class="ingredient-list">
"""
                        for ingredient in recipe.recipe_ingredients:
                            if (
                                ingredient.quantity
                                and ingredient.quantity > 0
                                and ingredient.measurement
                                and not (
                                    ingredient.quantity == 1.0
                                    and ingredient.measurement == "unit"
                                )
                            ):
                                html_body += f"                    <li>{ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}</li>\n"
                            else:
                                html_body += f"                    <li>{ingredient.ingredient_name}</li>\n"

                        html_body += """                </ul>
"""

                        if recipe.notes:
                            html_body += f"""                <div class="notes">
                    <strong>Instructions/Notes:</strong><br>
                    {recipe.notes.replace(chr(10), "<br>")}
                </div>
"""

                        html_body += """            </div>
"""

            html_body += """        </div>
        <div class="footer">
            <p>Auto-Cart - Smart Household Grocery Management</p>
        </div>
    </div>
</body>
</html>
"""

            # Build plain text version
            text_body = f"Your Grocery List: {grocery_list.name}\n\n"
            text_body += "=" * 50 + "\n"

            for recipe_ingredient in grocery_list.recipe_ingredients:
                if (
                    recipe_ingredient.quantity
                    and recipe_ingredient.quantity > 0
                    and recipe_ingredient.measurement
                    and not (
                        recipe_ingredient.quantity == 1.0
                        and recipe_ingredient.measurement == "unit"
                    )
                ):
                    text_body += f"• {recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}\n"
                else:
                    text_body += f"• {recipe_ingredient.ingredient_name}\n"

            if selected_recipe_ids:
                recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()
                if recipes:
                    text_body += (
                        "\n\n" + "=" * 50 + "\nSELECTED RECIPES\n" + "=" * 50 + "\n\n"
                    )

                    for recipe in recipes:
                        text_body += f"RECIPE: {recipe.name}\n"
                        if recipe.url:
                            text_body += f"URL: {recipe.url}\n"

                        text_body += "\nINGREDIENTS:\n"
                        for ingredient in recipe.recipe_ingredients:
                            if (
                                ingredient.quantity
                                and ingredient.quantity > 0
                                and ingredient.measurement
                                and not (
                                    ingredient.quantity == 1.0
                                    and ingredient.measurement == "unit"
                                )
                            ):
                                text_body += f"• {ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}\n"
                            else:
                                text_body += f"• {ingredient.ingredient_name}\n"

                        if recipe.notes:
                            text_body += f"\nINSTRUCTIONS/NOTES:\n{recipe.notes}\n"

                        text_body += "\n" + "-" * 30 + "\n\n"

            text_body += "\n---\nAuto-Cart - Smart Household Grocery Management"

            msg = Message(
                "Your Grocery List & Recipes",
                recipients=[recipient],
                body=text_body,
                html=html_body,
            )
            mail.send(msg)

        except Exception as e:
            logger.error(f"Failed to send grocery list email: {e}", exc_info=True)
            raise e

    @classmethod
    def send_recipes_only_email(cls, recipient, selected_recipe_ids, mail):
        """Send only the selected recipes via email."""
        try:
            # Build HTML email body
            html_body = """
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #004c91 0%, #1e6bb8 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 5px 5px 0 0; }
        .logo { width: 50px; height: 50px; margin-bottom: 10px; }
        .content { background-color: #f9f9f9; padding: 30px; border: 1px solid #ddd; border-top: none; }
        .recipe-section { background-color: white; padding: 20px; margin: 20px 0; border-left: 4px solid #ff6600; border-radius: 5px; }
        .ingredient-list { list-style: none; padding-left: 0; }
        .ingredient-list li { padding: 8px 0; border-bottom: 1px solid #eee; }
        .ingredient-list li:last-child { border-bottom: none; }
        .recipe-title { color: #004c91; margin-top: 0; }
        .recipe-url { color: #ff6600; text-decoration: none; word-break: break-all; }
        .recipe-url:hover { text-decoration: underline; }
        .notes { background-color: #f0f8ff; padding: 15px; border-radius: 5px; margin-top: 15px; font-style: italic; }
        .footer { text-align: center; padding: 20px; color: #999; font-size: 12px; border-radius: 0 0 5px 5px; background-color: #f9f9f9; border: 1px solid #ddd; border-top: none; }
        .no-recipes { text-align: center; padding: 40px; color: #999; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="logo">
                <circle cx="50" cy="50" r="48" fill="#FF8C42"/>
                <g transform="translate(50, 52)">
                    <path d="M -26 -20 L -20 8 L 20 8 L 24 -20 Z" fill="#007bff" stroke="#004c91" stroke-width="2.5"/>
                    <path d="M -28 -20 L -32 -32 L -20 -32" fill="none" stroke="#007bff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <circle cx="-10" cy="16" r="5" fill="#004c91"/>
                    <circle cx="10" cy="16" r="5" fill="#004c91"/>
                    <line x1="-16" y1="-14" x2="-16" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="-5" y1="-14" x2="-5" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="6" y1="-14" x2="6" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="16" y1="-14" x2="16" y2="5" stroke="white" stroke-width="2"/>
                </g>
            </svg>
            <h1 style="margin: 10px 0 0 0; font-size: 24px;">Your Recipes</h1>
        </div>
        <div class="content">
"""

            # Build plain text version
            text_body = ""

            if selected_recipe_ids:
                recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()
                if recipes:
                    text_body = "Here are your selected recipes:\n\n"

                    for recipe in recipes:
                        html_body += f"""            <div class="recipe-section">
                <h3 class="recipe-title">📖 {recipe.name}</h3>
"""
                        if recipe.url:
                            html_body += f"""                <p><strong>Recipe URL:</strong> <a href="{recipe.url}" class="recipe-url">{recipe.url}</a></p>
"""

                        html_body += """                <h4 style="color: #ff6600; margin-top: 20px;">Ingredients:</h4>
                <ul class="ingredient-list">
"""

                        # Plain text version
                        text_body += f"RECIPE: {recipe.name}\n"
                        if recipe.url:
                            text_body += f"URL: {recipe.url}\n"
                        text_body += "\nINGREDIENTS:\n"

                        for ingredient in recipe.recipe_ingredients:
                            if (
                                ingredient.quantity
                                and ingredient.quantity > 0
                                and ingredient.measurement
                                and not (
                                    ingredient.quantity == 1.0
                                    and ingredient.measurement == "unit"
                                )
                            ):
                                html_body += f"                    <li>{ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}</li>\n"
                                text_body += f"• {ingredient.quantity} {ingredient.measurement} {ingredient.ingredient_name}\n"
                            else:
                                html_body += f"                    <li>{ingredient.ingredient_name}</li>\n"
                                text_body += f"• {ingredient.ingredient_name}\n"

                        html_body += """                </ul>
"""

                        if recipe.notes:
                            html_body += f"""                <div class="notes">
                    <strong>Instructions/Notes:</strong><br>
                    {recipe.notes.replace(chr(10), "<br>")}
                </div>
"""
                            text_body += f"\nINSTRUCTIONS/NOTES:\n{recipe.notes}\n"

                        html_body += """            </div>
"""
                        text_body += "\n" + "-" * 30 + "\n\n"
                else:
                    html_body += """            <div class="no-recipes">
                <p>No recipes selected.</p>
            </div>
"""
                    text_body = "No recipes selected."
            else:
                html_body += """            <div class="no-recipes">
                <p>No recipes selected.</p>
            </div>
"""
                text_body = "No recipes selected."

            html_body += """        </div>
        <div class="footer">
            <p>Auto-Cart - Smart Household Grocery Management</p>
        </div>
    </div>
</body>
</html>
"""

            text_body += "\n---\nAuto-Cart - Smart Household Grocery Management"

            msg = Message(
                "Your Recipes", recipients=[recipient], body=text_body, html=html_body
            )
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
            ingredients_text = "\n".join(
                [
                    f"{ing['quantity']} {ing['measurement']} {ing['ingredient_name']}"
                    for ing in ingredients_list
                ]
            )

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
                    {
                        "role": "user",
                        "content": f"Consolidate these ingredients:\n\n{ingredients_text}",
                    },
                ],
                temperature=0.1,
                max_tokens=1000,
            )

            consolidated_text = response.choices[0].message.content.strip()

            # Parse the consolidated ingredients back into the expected format
            consolidated_ingredients = []
            for line in consolidated_text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # Parse the consolidated ingredient - improved regex to handle mixed numbers and decimals
                # Matches: "2 cups flour", "1/2 cup sugar", "1.5 lb beef", "2 1/2 tbsp salt"
                match = re.match(
                    r"^(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s+(\S+)\s+(.*)", line
                )
                if match:
                    quantity, measurement, ingredient_name = match.groups()
                    consolidated_ingredients.append(
                        {
                            "quantity": quantity.strip(),
                            "measurement": measurement.strip(),
                            "ingredient_name": ingredient_name.strip(),
                        }
                    )
                else:
                    # Fallback: if parsing fails, keep the ingredient with default values
                    logger.warning(f"Could not parse consolidated ingredient: {line}")
                    consolidated_ingredients.append(
                        {
                            "quantity": "1",
                            "measurement": "unit",
                            "ingredient_name": line,
                        }
                    )

            return consolidated_ingredients

        except Exception as e:
            logger.error(f"OpenAI ingredient consolidation error: {e}", exc_info=True)
            logger.info("Falling back to original ingredients")
            return ingredients_list


class MealPlanChange(db.Model):
    """Track meal plan changes for daily summary emails"""

    __tablename__ = "meal_plan_changes"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id"), nullable=False)
    change_type = db.Column(db.String(20), nullable=False)  # 'added', 'updated', 'deleted'
    meal_name = db.Column(db.Text, nullable=False)
    meal_date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # 'breakfast', 'lunch', 'dinner'
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=get_est_now)
    emailed = db.Column(db.Boolean, default=False, nullable=False)

    # Optional: store what changed for updates
    change_details = db.Column(db.Text, nullable=True)  # JSON string with details

    household = db.relationship("Household", backref="meal_plan_changes")
    changed_by = db.relationship("User", backref="meal_plan_changes")


def connect_db(app):
    db.app = app
    db.init_app(app)
