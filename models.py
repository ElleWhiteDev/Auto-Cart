import json
import re
from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from flask import g
from flask_mail import Message
import anthropic
from utils import (
    parse_quantity_string,
    parse_simple_ingredient,
    is_valid_float,
    get_est_now,
)
from logging_config import logger

# Import db and bcrypt from extensions to avoid circular imports
from extensions import db, bcrypt

# Reads ANTHROPIC_API_KEY from the environment
ai_client = anthropic.Anthropic()
AI_MODEL = "claude-opus-5-5"

# JSON shape Recipe.parse_ingredients asks Claude for
_PARSED_INGREDIENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quantity": {"type": "string"},
                    "measurement": {"type": "string"},
                    "ingredient_name": {"type": "string"},
                },
                "required": ["quantity", "measurement", "ingredient_name"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ingredients"],
    "additionalProperties": False,
}


def _ask_claude(system_prompt: str, user_content: str, json_schema=None) -> str:
    """Send one prompt to Claude and return its text reply.

    With json_schema, the reply is guaranteed to be JSON matching that schema.
    Raises on API errors or a refusal so callers can fall back.
    """
    output_config = {"effort": "low"}
    if json_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}

    response = ai_client.beta.messages.create(
        model=AI_MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_config=output_config,
        # On a safety refusal, re-run on a fallback model chosen by the API
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined the request")
    return next(block.text for block in response.content if block.type == "text").strip()


_MEASUREMENT_ALIASES = {
    "cup": "cup",
    "cups": "cup",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbs": "tbsp",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "unit": "unit",
    "units": "unit",
    "can": "unit",
    "cans": "unit",
}
_CANONICAL_MEASUREMENTS = set(_MEASUREMENT_ALIASES.values())
_PREP_WORDS = {"chopped", "minced", "diced", "sliced", "cubed"}
_NON_PURCHASE_NOTE_WORDS = {"optional", "divided"}
_WORD_NORMALIZATIONS = {
    "onions": "onion",
    "breasts": "breast",
    "thighs": "thigh",
}
_TOMATO_PRODUCT_WORDS = {"sauce", "paste", "puree", "salsa", "juice", "soup"}
_PACKAGE_SIZE_MEASUREMENTS = {"oz", "g", "kg", "ml", "l"}
_WATER_DESCRIPTORS = {"water", "warm", "cold", "hot", "boiling", "ice", "iced"}


def _format_quantity(quantity: float) -> str:
    """Format numeric quantities into stable strings."""
    if float(quantity).is_integer():
        return str(int(quantity))
    return f"{quantity:.4f}".rstrip("0").rstrip(".")


def _normalize_measurement(measurement: Any) -> str:
    """Normalize measurements to the grocery-list canonical set."""
    normalized = str(measurement or "unit").strip().lower()
    return _MEASUREMENT_ALIASES.get(normalized, normalized or "unit")


def _normalize_ingredient_name(ingredient_name: Any) -> str:
    """Normalize ingredient names while preserving purchase-critical distinctions."""
    normalized = re.sub(r"\s+", " ", str(ingredient_name or "").strip().lower())
    normalized = re.sub(r"[^a-z0-9\s./\-]", "", normalized)
    tokens = [
        token
        for token in normalized.split()
        if token not in _PREP_WORDS and token not in _NON_PURCHASE_NOTE_WORDS
    ]
    tokens = [_WORD_NORMALIZATIONS.get(token, token) for token in tokens]

    if not tokens:
        return normalized or "ingredient"

    has_tomato_product_word = any(token in _TOMATO_PRODUCT_WORDS for token in tokens)
    if not has_tomato_product_word and any(
        token in {"tomato", "tomatoes"} for token in tokens
    ):
        tokens = [
            "tomatoes" if token in {"tomato", "tomatoes"} else token for token in tokens
        ]

    return " ".join(tokens)


def _is_water_ingredient(ingredient_name: str) -> bool:
    """Return True when the ingredient is effectively just a water line."""
    tokens = ingredient_name.split()
    return (
        bool(tokens)
        and tokens[-1] == "water"
        and all(token in _WATER_DESCRIPTORS for token in tokens)
    )


_CONSOLIDATED_LINE_RE = re.compile(r"^(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s+(\S+)\s+(.*)")


def _parse_consolidated_line(line: str) -> Dict[str, str]:
    """Parse a "quantity measurement ingredient_name" line from the consolidation model.

    Quantities may be whole ("2"), decimal ("1.5"), fractional ("1/2") or mixed ("2 1/2").
    Lines that don't fit are kept as "1 unit <line>" so nothing is silently dropped.
    """
    line = line.strip()
    match = _CONSOLIDATED_LINE_RE.match(line)
    if not match:
        logger.warning(f"Could not parse consolidated ingredient: {line}")
        return {"quantity": "1", "measurement": "unit", "ingredient_name": line}

    quantity, measurement, ingredient_name = match.groups()
    return {
        "quantity": quantity.strip(),
        "measurement": measurement.strip(),
        "ingredient_name": ingredient_name.strip(),
    }


def _normalize_ingredient_entry(ingredient: Dict[str, Any]) -> Dict[str, str]:
    """Normalize a parsed ingredient entry."""
    return {
        "quantity": str(ingredient.get("quantity", "1")).strip() or "1",
        "measurement": _normalize_measurement(ingredient.get("measurement", "unit")),
        "ingredient_name": _normalize_ingredient_name(
            ingredient.get("ingredient_name", "ingredient")
        ),
    }


def _resolve_unit_rows(rows: List[Dict[str, Any]]) -> None:
    """Rewrite one ingredient's vague "unit" rows into its real measurement, in place.

    Only applies when the ingredient's other rows all share one real measurement;
    otherwise the "unit" rows are left as-is rather than guessed at.
    - Package measurements (oz, g, ml, ...) count each unit as one package, and
      only when every sized row agrees on the package size:
      "14.5 oz tomatoes" + "1 unit tomatoes" -> 29 oz tomatoes
    - Any other measurement counts each unit as one of that measurement:
      "1 lb ground beef" + "1 unit ground beef" -> 2 lb ground beef
    """
    unit_rows = [
        r for r in rows if r["measurement"] == "unit" and r["_quantity_value"] is not None
    ]
    real_rows = [r for r in rows if r["measurement"] != "unit"]
    real_measurements = {r["measurement"] for r in real_rows}
    if not unit_rows or len(real_measurements) != 1:
        return

    measurement = next(iter(real_measurements))
    size_per_unit = 1.0
    if measurement in _PACKAGE_SIZE_MEASUREMENTS:
        package_sizes = {r["_quantity_value"] for r in real_rows}
        if len(package_sizes) != 1 or None in package_sizes:
            return
        size_per_unit = next(iter(package_sizes))

    for row in unit_rows:
        row["measurement"] = measurement
        row["_quantity_value"] *= size_per_unit
        row["quantity"] = _format_quantity(row["_quantity_value"])


def _merge_ingredient_entries(
    ingredients_list: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Deterministically normalize and merge grocery ingredients.

    1. Normalize every row and drop plain water.
    2. Per ingredient, fold vague "unit" rows into its real measurement.
    3. Sum rows sharing (ingredient_name, measurement), keeping first-seen order.
    """
    rows = []
    for ingredient in ingredients_list:
        row = _normalize_ingredient_entry(ingredient)
        if _is_water_ingredient(row["ingredient_name"]):
            continue
        row["_quantity_value"] = parse_quantity_string(row["quantity"])
        rows.append(row)

    rows_by_name = defaultdict(list)
    for row in rows:
        rows_by_name[row["ingredient_name"]].append(row)
    for name_rows in rows_by_name.values():
        _resolve_unit_rows(name_rows)

    merged = {}
    for row in rows:
        key = (row["ingredient_name"], row["measurement"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = row
        elif (
            existing["_quantity_value"] is not None
            and row["_quantity_value"] is not None
        ):
            existing["_quantity_value"] += row["_quantity_value"]
            existing["quantity"] = _format_quantity(existing["_quantity_value"])

    return [
        {
            "quantity": row["quantity"],
            "measurement": row["measurement"],
            "ingredient_name": row["ingredient_name"],
        }
        for row in merged.values()
    ]


class Household(db.Model):
    """Household/family group for collaboration.

    A household can have multiple owners and members. Profiles (users) can belong to
    multiple households - they can be owners of some and members of others.
    All recipes and pantry lists are scoped to households.
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

    def get_owners(self) -> List["HouseholdMember"]:
        """Get all owner members of this household"""
        return [m for m in self.members if m.is_owner()]

    def get_regular_members(self) -> List["HouseholdMember"]:
        """Get all non-owner members of this household"""
        return [m for m in self.members if not m.is_owner()]

    def is_user_owner(self, user_id: int) -> bool:
        """Check if a user is an owner of this household"""
        membership = HouseholdMember.query.filter_by(
            household_id=self.id, user_id=user_id
        ).first()
        return membership and membership.is_owner()

    def is_user_member(self, user_id: int) -> bool:
        """Check if a user is a member (owner or regular) of this household"""
        membership = HouseholdMember.query.filter_by(
            household_id=self.id, user_id=user_id
        ).first()
        return membership is not None

    def get_connected_households(self) -> List["Household"]:
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

    def __repr__(self) -> str:
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
    receive_meal_plan_emails = db.Column(db.Boolean, nullable=False, default=True)
    receive_chef_assignment_emails = db.Column(db.Boolean, nullable=False, default=True)
    receive_weekly_reminder_emails = db.Column(db.Boolean, nullable=False, default=True)

    user = db.relationship("User", backref="household_memberships")

    def is_owner(self) -> bool:
        """Check if this membership has owner privileges"""
        return self.role == "owner"

    def is_member(self) -> bool:
        """Check if this is a regular member (not owner)"""
        return self.role == "member"

    def __repr__(self) -> str:
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

            # Get user's assigned meals (check both legacy single cook and new multi-cook)
            my_meals = []
            for entry in meal_entries:
                # Check legacy single cook field
                if entry.assigned_cook_user_id == user_id:
                    my_meals.append(entry)
                    continue
                # Check new multi-cook relationship (lazy='dynamic' returns a query)
                if entry.assigned_cooks.filter_by(id=user_id).first():
                    my_meals.append(entry)
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
                <circle cx="50" cy="50" r="48" fill="#ff6600"/>
                <g transform="translate(50, 52)">
                    <path d="M -26 -20 L -20 8 L 20 8 L 24 -20 Z" fill="#1e6bb8" stroke="#004c91" stroke-width="2.5"/>
                    <path d="M -28 -20 L -32 -32 L -20 -32" fill="none" stroke="#1e6bb8" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
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

    # Optional default pantry list Alexa should use for this user
    alexa_default_grocery_list_id = db.Column(
        db.Integer,
        db.ForeignKey("grocery_lists.id", ondelete="SET NULL"),
        nullable=True,
    )

    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    last_activity = db.Column(db.DateTime, nullable=True)

    # Password reset fields
    reset_token = db.Column(db.Text, nullable=True, unique=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    recipes = db.relationship("Recipe", backref="user", cascade="all, delete-orphan")
    grocery_lists = db.relationship(
        "GroceryList",
        backref="user",
        cascade="all, delete-orphan",
        foreign_keys="GroceryList.user_id",
    )

    # Direct relationship to the user's Alexa default pantry list (if configured)
    alexa_default_grocery_list = db.relationship(
        "GroceryList", foreign_keys=[alexa_default_grocery_list_id]
    )

    def get_households(self) -> List[Household]:
        """Get all households this user is a member of"""
        return [m.household for m in self.household_memberships]

    def get_owned_households(self) -> List[Household]:
        """Get all households this user owns"""
        return [m.household for m in self.household_memberships if m.is_owner()]

    def get_member_households(self) -> List[Household]:
        """Get all households where this user is a regular member (not owner)"""
        return [m.household for m in self.household_memberships if m.is_member()]

    def __repr__(self) -> str:
        return f"<User #{self.id}: {self.username}, {self.email}>"

    def change_password(
        self, current_password: str, new_password: str, new_password_confirm: str
    ) -> None:
        """Change password"""

        if not bcrypt.check_password_hash(self.password, current_password):
            raise ValueError("Current password is incorrect.")
        if new_password != new_password_confirm:
            raise ValueError("New passwords do not match.")
        self.password = bcrypt.generate_password_hash(new_password).decode("UTF-8")

    @classmethod
    def signup(cls, username: str, email: str, password: str) -> "User":
        """Sign up user.

        Hashes password and adds user to system.
        """

        hashed_pwd = bcrypt.generate_password_hash(password).decode("UTF-8")

        user = User(username=username, email=email, password=hashed_pwd)

        db.session.add(user)
        return user

    @classmethod
    def authenticate(cls, username: str, password: str) -> Optional["User"]:
        """Find user with `username` and `password`.

        Username lookup is case-insensitive.
        """
        from logging_config import logger

        # Case-insensitive username lookup
        user = cls.query.filter(db.func.lower(cls.username) == username.lower()).first()

        if user:
            logger.debug(
                f"User.authenticate: Found user '{user.username}', checking password..."
            )
            is_auth = bcrypt.check_password_hash(user.password, password)
            if is_auth:
                logger.debug(
                    f"User.authenticate: Password check PASSED for '{user.username}'"
                )
                return user
            else:
                logger.debug(
                    f"User.authenticate: Password check FAILED for '{user.username}'"
                )
        else:
            logger.debug(f"User.authenticate: No user found for username '{username}'")

        return None

    def generate_reset_token(self) -> str:
        """Generate a password reset token that expires in 1 hour"""
        import secrets
        from datetime import timedelta

        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expiry = get_est_now() + timedelta(hours=1)
        return self.reset_token

    def generate_password_reset_token(self) -> str:
        """Alias used by the auth routes."""
        return self.generate_reset_token()

    @classmethod
    def verify_reset_token(cls, token: str) -> Optional["User"]:
        """Verify a reset token and return the user if valid"""
        user = cls.query.filter_by(reset_token=token).first()

        if not user or not user.reset_token_expiry:
            return None

        # Check if token has expired
        if get_est_now() > user.reset_token_expiry:
            return None

        return user

    def reset_password(self, new_password: str) -> None:
        """Reset password using a reset token"""
        self.password = bcrypt.generate_password_hash(new_password).decode("UTF-8")
        self.reset_token = None
        self.reset_token_expiry = None

    def send_password_reset_email(self, mail) -> None:
        """Send password reset instructions to the user."""
        from flask import current_app, request
        from flask_mail import Message

        base_url = request.url_root.rstrip("/")
        reset_url = f"{base_url}/reset-password/{self.reset_token}"
        response_email = current_app.config.get("MAIL_DEFAULT_SENDER", "support@autocart.com")
        subject = "Reset Your Auto-Cart Password"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #004c91; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }}
        .button {{ display: inline-block; padding: 12px 28px; background-color: #004c91; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
        .warning {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔐 Password Reset Request</h1>
        </div>
        <div class="content">
            <p>Hello {self.username},</p>
            <p>We received a request to reset your Auto-Cart password. Click the button below to create a new password:</p>
            <div style="text-align: center;">
                <a href="{reset_url}" class="button" style="color: white !important;">Reset My Password</a>
            </div>
            <p>Or paste this link directly into your browser:</p>
            <div style="word-break: break-all; background-color: #fff; padding: 10px; border: 1px solid #ddd; border-radius: 3px;">
                {reset_url}
            </div>
            <div class="warning">
                <strong>This link expires in 1 hour.</strong>
            </div>
            <p>If you didn't request this, ignore this email and your password stays secure.</p>
            <div class="footer">
                <p>Auto-Cart — Need help? Reply to {response_email}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
Password Reset Request

Use the link below to reset your Auto-Cart password:
{reset_url}

This link expires in 1 hour.

If you didn't request it, ignore this email.
"""

        msg = Message(
            subject,
            recipients=[self.email],
            html=html_body,
            body=text_body,
        )
        mail.send(msg)


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
    tags = db.relationship(
        "RecipeTag",
        secondary="recipe_tags_assoc",
        backref="recipes",
        lazy="subquery",
    )

    @classmethod
    def clean_ingredients_with_ai(cls, ingredients_text):
        """Clean and standardize scraped ingredients using Claude."""
        try:
            system_prompt = """You clean raw recipe ingredient text for a grocery and meal-planning app.

Primary goal:
- Convert messy scraped ingredient input into clean, human-readable ingredient lines that are easy for a user to review and easy for a later parser to interpret.

How to process the input:
- Treat each meaningful ingredient independently.
- Preserve the original ingredient order of retained lines.
- Keep exactly one logical ingredient per output line.

Input may contain:
- bullets, checkboxes, OCR artifacts, merged tokens, unicode fractions, section headers, serving-count text, blank lines, and inconsistent spacing.

Cleaning rules:
1) Repair obvious token merges and spacing:
   - "1/4cuphoney" -> "1/4 cup honey"
2) Remove non-ingredient noise:
   - checkboxes (▢☐□✓✔), bullets, repeated punctuation, stray symbols, standalone section headers, serving-count text, and blank lines.
3) Normalize explicit quantities when safe:
   - convert unicode fractions to ASCII fractions: ½ -> 1/2, ¼ -> 1/4, ¾ -> 3/4
   - normalize exact decimals to simple fractions when obvious: 0.25 -> 1/4, 0.5 -> 1/2, 0.75 -> 3/4, 0.33 -> 1/3, 0.67 -> 2/3
4) Normalize units to canonical forms when the unit is explicit:
   - tablespoon/tablespoons/tb/T -> tbsp
   - teaspoon/teaspoons/t -> tsp
   - cup/cups/c/C -> cup
   - ounce/ounces -> oz
   - pound/pounds/lbs -> lb
   - gram/grams -> g
   - kilogram/kilograms -> kg
   - milliliter/milliliters -> ml
   - liter/litre/liters/litres -> l
5) Preserve shopping-relevant descriptors and helpful prep wording:
   - keep descriptors like yellow, red, unsalted, whole, fresh, frozen, ground, boneless, skinless
   - keep prep words like diced, minced, chopped, grated, crushed when they help the user review the ingredient text
   - keep package sizes: "1 (14.5 oz) can diced tomatoes" stays as written
6) Drop obviously non-purchase notes when they are not part of the core ingredient:
   - optional, divided, plus more for serving, for garnish, as needed
7) Never invent missing ingredients, quantities, or units.
   - If a quantity or unit is absent, keep the line readable instead of guessing.

Output contract:
- Return plain text only.
- No headings, numbering, commentary, markdown, or code fences.
- Return one cleaned ingredient per line.
- Do not add any explanation before or after the cleaned lines."""

            return _ask_claude(
                system_prompt, f"Clean these ingredients:\n\n{ingredients_text}"
            )

        except Exception as e:
            logger.error(f"AI ingredient cleaning error: {e}", exc_info=True)
            logger.info("Falling back to original ingredients text")
            return ingredients_text

    @classmethod
    def parse_ingredients(cls, ingredients_text, allow_fallback=True):
        """Parse ingredient text into individual objects using Claude.

        If the Claude call fails, falls back to simple regex parsing, or re-raises
        when allow_fallback is False.
        """

        try:
            system_prompt = """You parse recipe ingredient lines into structured objects for a grocery and meal-planning app.

Processing rules:
- Treat each non-empty ingredient line independently.
- Preserve input order.
- Return exactly one object per meaningful ingredient line.
- Ignore blank lines and lines that are clearly section headers or other non-ingredient text.

Return format:
- Return a JSON object whose "ingredients" array holds one object per ingredient line, with string keys "quantity", "measurement" and "ingredient_name".

Field rules:
1) Quantity:
   - Keep numeric quantities as strings (examples: "2", "1/2", "2 1/2", "1.5").
   - Normalize common unicode fractions to ASCII equivalents when present.
   - For ranges like "3-4", use the first value ("3").
   - If quantity is missing or non-numeric (for example: "to taste", "as needed", "a pinch"), use "1".
2) Measurement:
   - Allowed canonical values: cup, tbsp, tsp, lb, oz, g, kg, ml, l, unit.
   - Normalize plurals and aliases to those singular canonical forms.
   - If the source uses an unsupported or extra-specific unit (for example: clove, can, stick, bunch, sprig, pinch, dash, package, slice), use "unit" instead of inventing a new measurement.
   - Exception: when a can or package states its size, use that size times the count: "2 (15 oz) cans black beans" -> quantity "30", measurement "oz".
3) Ingredient name:
   - Keep the shoppable ingredient or product name.
   - Remove prep-only descriptors wherever they appear: chopped, minced, diced, sliced, cubed.
   - Preserve purchase-critical distinctions such as yellow onion, red onion, unsalted butter, whole milk, fresh basil, dried basil, chicken thigh, chicken breast, ground beef, tomato sauce.
   - Remove clearly non-purchase notes like optional, divided, for serving, for garnish, as needed.
   - Treat "diced tomatoes" as "tomatoes", but keep products like "tomato sauce", "tomato paste", and "salsa" distinct.
4) Never merge, deduplicate, summarize, or omit any meaningful ingredient line.

Examples:
"2 cups flour" -> {"quantity":"2","measurement":"cup","ingredient_name":"flour"}
"1/4 tsp salt" -> {"quantity":"1/4","measurement":"tsp","ingredient_name":"salt"}
"3-4 lb chicken thighs" -> {"quantity":"3","measurement":"lb","ingredient_name":"chicken thighs"}
"14.5 oz diced tomatoes" -> {"quantity":"14.5","measurement":"oz","ingredient_name":"tomatoes"}
"1 (14.5 oz) can diced tomatoes" -> {"quantity":"14.5","measurement":"oz","ingredient_name":"tomatoes"}
"1 cup yellow onion, diced" -> {"quantity":"1","measurement":"cup","ingredient_name":"yellow onion"}
"milk" -> {"quantity":"1","measurement":"unit","ingredient_name":"milk"}
"salt and pepper to taste" -> {"quantity":"1","measurement":"unit","ingredient_name":"salt and pepper to taste"}"""

            reply = _ask_claude(
                system_prompt,
                f"Parse these ingredients:\n\n{ingredients_text}",
                json_schema=_PARSED_INGREDIENTS_SCHEMA,
            )
            parsed_ingredients = json.loads(reply)["ingredients"]
            return [
                _normalize_ingredient_entry(ingredient)
                for ingredient in parsed_ingredients
            ]

        except Exception as e:
            if not allow_fallback:
                raise
            logger.error(f"AI ingredient parsing error: {e}", exc_info=True)
            logger.info("Falling back to simple parsing")

            parsed_ingredients = []
            for line in ingredients_text.split("\n"):
                for ingredient in parse_simple_ingredient(line):
                    # "3 large eggs" parses "large" as the measurement; fold it back
                    # into the name unless it's a unit we recognise.
                    if (
                        _normalize_measurement(ingredient["measurement"])
                        not in _CANONICAL_MEASUREMENTS
                    ):
                        ingredient = {
                            "quantity": ingredient["quantity"],
                            "measurement": "unit",
                            "ingredient_name": f"{ingredient['measurement']} {ingredient['ingredient_name']}",
                        }
                    parsed_ingredients.append(_normalize_ingredient_entry(ingredient))
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
        """Create a recipe object with its ingredients parsed from text."""

        recipe = cls(
            url=url,
            user_id=user_id,
            name=name,
            notes=notes,
            household_id=household_id,
            visibility=visibility,
        )

        recipe.recipe_ingredients.extend(cls.build_ingredients(ingredients_text))
        return recipe

    @classmethod
    def build_ingredients(cls, ingredients_text, allow_fallback=True):
        """Parse ingredient text into RecipeIngredient rows ready to attach to a recipe."""
        ingredients = []
        for ingredient_data in cls.parse_ingredients(ingredients_text, allow_fallback):
            ingredient_name = (ingredient_data.get("ingredient_name") or "").strip()
            if not ingredient_name:
                continue

            quantity = parse_quantity_string(str(ingredient_data.get("quantity") or ""))
            ingredients.append(
                RecipeIngredient(
                    quantity=1.0 if quantity is None else quantity,
                    measurement=ingredient_data.get("measurement") or "unit",
                    # ingredient_name is a String(40) column
                    ingredient_name=ingredient_name[:40],
                )
            )
        return ingredients


class GroceryListItem(db.Model):
    """Association object for pantry list items with metadata"""

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
    """Pantry List of ingredients scoped to a household.

    Pantry lists belong to a household and can be collaboratively managed by all
    household members. Users can access pantry lists from all households they belong to.
    """

    __tablename__ = "grocery_lists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=True
    )
    name = db.Column(db.Text, nullable=False, default="My Pantry List")
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
        """Add selected recipes to current pantry list (append, not replace)"""

        recipes = Recipe.query.filter(Recipe.id.in_(selected_recipe_ids)).all()

        # Collect all ingredients - START WITH EXISTING ONES from the pantry list
        all_ingredients = []

        # Add existing ingredients from the pantry list
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
        consolidated_ingredients = cls.consolidate_ingredients_with_ai(
            all_ingredients
        )

        if grocery_list is not None:
            # NOW clear and rebuild with consolidated list (which includes both old and new)
            for item in grocery_list.items:
                db.session.delete(item)

        # Create new recipe ingredients and pantry list items from consolidated list
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

            # Create pantry list item
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
        """Send the pantry list and selected recipes via email."""
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
                <circle cx="50" cy="50" r="48" fill="#ff6600"/>
                <g transform="translate(50, 52)">
                    <path d="M -26 -20 L -20 8 L 20 8 L 24 -20 Z" fill="#1e6bb8" stroke="#004c91" stroke-width="2.5"/>
                    <path d="M -28 -20 L -32 -32 L -20 -32" fill="none" stroke="#1e6bb8" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <circle cx="-10" cy="16" r="5" fill="#004c91"/>
                    <circle cx="10" cy="16" r="5" fill="#004c91"/>
                    <line x1="-16" y1="-14" x2="-16" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="-5" y1="-14" x2="-5" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="6" y1="-14" x2="6" y2="5" stroke="white" stroke-width="2"/>
                    <line x1="16" y1="-14" x2="16" y2="5" stroke="white" stroke-width="2"/>
                </g>
            </svg>
            <h1 style="margin: 10px 0 0 0; font-size: 24px;">Your Pantry List & Recipes</h1>
        </div>
        <div class="content">
            <div class="grocery-section">
                <h2 style="color: #004c91; margin-top: 0;">🛒 Pantry List: {grocery_list.name}</h2>
                <ul class="ingredient-list">
"""

            # Look up household staples so we can annotate them in the email
            staple_names: set = set()
            if grocery_list.household_id:
                from models import PantryStaple
                staple_names = {
                    s.ingredient_name
                    for s in PantryStaple.query.filter_by(
                        household_id=grocery_list.household_id
                    ).all()
                }

            # Add pantry list items
            for recipe_ingredient in grocery_list.recipe_ingredients:
                is_staple = recipe_ingredient.ingredient_name.lower() in staple_names
                staple_note = ' <span style="color:#9ca3af;font-size:0.85em;">(have it)</span>' if is_staple else ""
                item_style = ' style="color:#9ca3af;"' if is_staple else ""
                if (
                    recipe_ingredient.quantity
                    and recipe_ingredient.quantity > 0
                    and recipe_ingredient.measurement
                    and not (
                        recipe_ingredient.quantity == 1.0
                        and recipe_ingredient.measurement == "unit"
                    )
                ):
                    html_body += f"                    <li{item_style}>✓ {recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}{staple_note}</li>\n"
                else:
                    html_body += f"                    <li{item_style}>✓ {recipe_ingredient.ingredient_name}{staple_note}</li>\n"

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
            text_body = f"Your Pantry List: {grocery_list.name}\n\n"
            text_body += "=" * 50 + "\n"

            for recipe_ingredient in grocery_list.recipe_ingredients:
                is_staple = recipe_ingredient.ingredient_name.lower() in staple_names
                staple_suffix = " (have it)" if is_staple else ""
                if (
                    recipe_ingredient.quantity
                    and recipe_ingredient.quantity > 0
                    and recipe_ingredient.measurement
                    and not (
                        recipe_ingredient.quantity == 1.0
                        and recipe_ingredient.measurement == "unit"
                    )
                ):
                    text_body += f"• {recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}{staple_suffix}\n"
                else:
                    text_body += f"• {recipe_ingredient.ingredient_name}{staple_suffix}\n"

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
                "Your Pantry List & Recipes",
                recipients=[recipient],
                body=text_body,
                html=html_body,
            )
            mail.send(msg)

        except Exception as e:
            logger.error(f"Failed to send pantry list email: {e}", exc_info=True)
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
                <circle cx="50" cy="50" r="48" fill="#ff6600"/>
                <g transform="translate(50, 52)">
                    <path d="M -26 -20 L -20 8 L 20 8 L 24 -20 Z" fill="#1e6bb8" stroke="#004c91" stroke-width="2.5"/>
                    <path d="M -28 -20 L -32 -32 L -20 -32" fill="none" stroke="#1e6bb8" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
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
        """Format the pantry list for email."""
        ingredients_list = []
        for recipe_ingredient in self.recipe_ingredients:
            ingredient_detail = f"{recipe_ingredient.quantity} {recipe_ingredient.measurement} {recipe_ingredient.ingredient_name}"
            ingredients_list.append(ingredient_detail)

        return "\n".join(ingredients_list)

    @classmethod
    def consolidate_ingredients_with_ai(cls, ingredients_list):
        """Consolidate similar ingredients using Claude."""
        try:
            normalized_inputs = _merge_ingredient_entries(ingredients_list)

            # Format ingredients for AI processing
            ingredients_text = "\n".join(
                [
                    f"{ing['quantity']} {ing['measurement']} {ing['ingredient_name']}"
                    for ing in normalized_inputs
                ]
            )

            system_prompt = """You consolidate already-parsed grocery ingredients for a pantry list.

Primary goal:
- Reduce duplicate noise while keeping purchasing decisions correct.
- Replace vague "unit" measurements with the most likely real grocery unit when it can be confidently inferred.

Decision policy:
- Merge only when two lines are clearly the same shopping item.
- If there is any reasonable doubt, keep the items separate.
- Preserve input order based on the first retained line.
- Never invent new ingredients or omit non-water ingredients.

Always remove:
- water, warm water, cold water, hot water, boiling water, iced water

Keep these distinct when present:
- onion color or variety: yellow onion, red onion, white onion
- tomato varieties: roma tomatoes, cherry tomatoes, grape tomatoes
- tomato products: tomatoes vs tomato sauce vs tomato paste vs tomato puree vs salsa vs tomato juice vs tomato soup
- meat cut or form: chicken breast vs chicken thigh vs ground chicken
- milk fat or type: whole milk vs 2% milk vs skim milk
- cheese type: cheddar vs mozzarella vs parmesan
- butter type: salted butter vs unsalted butter
- fresh vs frozen vs dried variants when they change what should be bought

Allowed merges:
- prep-only wording differences: chopped/diced/minced/sliced/cubed/whole/halved onion -> onion (same for other produce)
- tomatoes and diced tomatoes -> tomatoes
- singular/plural forms and tiny wording variants that do not change what should be bought
- exact same ingredient with different quantities -> sum quantities
- explicit-size package lines can absorb matching unit/can lines only when the exact package size is known from another line for that same ingredient

Quantity and unit rules:
- Sum quantities for merged items.
- Preferred canonical units: cup, tbsp, tsp, lb, oz, g, kg, ml, l, unit.
- Do not guess cross-unit conversions (e.g. cups to oz).
- If exact conversion is unclear, keep a stable existing unit or keep items separate rather than inventing math.
- "unit" as a placeholder: when the same ingredient appears with both a real unit (lb, oz, cup, etc.) and a "unit" entry, treat the "unit" count as that many of the real unit and sum. Example: "1 lb ground beef" + "1 unit ground beef" -> "2 lb ground beef".

Unit inference — replace vague "unit" with a real grocery unit when confident:
- Countable whole items keep "unit" as-is (these are correct counts):
  egg, onion, lemon, lime, orange, avocado, apple, banana, potato, sweet potato,
  carrot, bell pepper, jalapeño, zucchini, cucumber, tomato (fresh whole), garlic head,
  garlic clove, shallot, corn on the cob, beet, turnip, artichoke, ear of corn
- Standard canned/packaged goods — replace "unit" with the standard US package size in oz:
  - chicken broth, beef broth, vegetable broth: 32 oz per unit
  - diced tomatoes, crushed tomatoes, whole peeled tomatoes (canned): 14.5 oz per unit
  - tomato sauce (canned): 15 oz per unit
  - tomato paste: 6 oz per unit
  - coconut milk (canned): 13.5 oz per unit
  - black beans, kidney beans, chickpeas, pinto beans, navy beans, white beans,
    cannellini beans, great northern beans (canned): 15 oz per unit
  - corn (canned): 15 oz per unit
  - green beans (canned): 14.5 oz per unit
  - pumpkin puree: 15 oz per unit
  - cream of mushroom soup, cream of chicken soup: 10.5 oz per unit
- All other "unit" ingredients: keep as "unit" — do not invent package sizes.

Examples:
- 1 unit chopped onion + 1 unit minced onion -> 2 unit onion
- 1 unit chicken broth + 1 unit chicken broth -> 64 oz chicken broth
- 14.5 oz diced tomatoes + 1 unit canned tomatoes -> 29 oz diced tomatoes
- 1 unit black beans -> 15 oz black beans
- 1 unit tomato paste -> 6 oz tomato paste
- 1 lb chicken breast + 1 lb chicken thigh -> keep as two separate lines
- 1 tbsp salted butter + 1 tbsp unsalted butter -> keep as two separate lines
- 1 tsp fresh basil + 1 tsp dried basil -> keep as two separate lines

Output contract:
- Return plain text only.
- Return one retained ingredient per line, exactly: "quantity measurement ingredient_name"
- No commentary, bullets, markdown, numbering, or extra text.

Before answering, verify that every retained non-water input line is represented either as its own output line or as part of a clearly merged equivalent output line."""

            consolidated_text = _ask_claude(
                system_prompt, f"Consolidate these ingredients:\n\n{ingredients_text}"
            )

            consolidated_ingredients = [
                _parse_consolidated_line(line)
                for line in consolidated_text.split("\n")
                if line.strip()
            ]

            return _merge_ingredient_entries(consolidated_ingredients)

        except Exception as e:
            logger.error(f"AI ingredient consolidation error: {e}", exc_info=True)
            logger.info("Falling back to deterministic consolidation")
            return _merge_ingredient_entries(ingredients_list)


# Association table for recipe tags (many-to-many)
recipe_tags_assoc = db.Table(
    "recipe_tags_assoc",
    db.Column(
        "recipe_id",
        db.Integer,
        db.ForeignKey("recipes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "tag_id",
        db.Integer,
        db.ForeignKey("recipe_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class RecipeTag(db.Model):
    """Tag that can be applied to recipes within a household."""

    __tablename__ = "recipe_tags"
    __table_args__ = (
        db.UniqueConstraint("household_id", "name", name="unique_household_tag"),
    )

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(50), nullable=False)

    household = db.relationship("Household", backref="tags")

    def __repr__(self):
        return f"<RecipeTag #{self.id}: {self.name}>"


class PantryStaple(db.Model):
    """Ingredient that the household always keeps stocked."""

    __tablename__ = "pantry_staples"
    __table_args__ = (
        db.UniqueConstraint(
            "household_id", "ingredient_name", name="unique_household_staple"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_name = db.Column(db.String(100), nullable=False)

    household = db.relationship("Household", backref="pantry_staples")

    def __repr__(self):
        return f"<PantryStaple #{self.id}: {self.ingredient_name}>"


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
