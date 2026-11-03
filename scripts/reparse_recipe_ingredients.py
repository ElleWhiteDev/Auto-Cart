"""Re-parse recipe ingredients that were saved as raw text.

From commit 5192015 (Aug 2025) until the Nov 2026 fix, the Add Recipe form stored
every ingredient line unparsed as "1 unit <line>" (truncated to 40 characters).
This re-parses those recipes from the stored lines.

A recipe is only touched when every ingredient is "1 unit" and at least one line
starts with a number, i.e. there is a quantity hidden in the name to recover.

Usage:
    python scripts/reparse_recipe_ingredients.py          # dry run, prints changes
    python scripts/reparse_recipe_ingredients.py --apply  # write changes
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app import app
from models import db, Recipe, GroceryListItem, RecipeIngredient
from utils import format_quantity

_STARTS_WITH_QUANTITY = re.compile(r"^\s*[\d½¼¾⅓⅔⅛]")


def _needs_reparse(recipe):
    ingredients = recipe.recipe_ingredients
    return (
        bool(ingredients)
        and all(i.quantity == 1 and i.measurement == "unit" for i in ingredients)
        and any(_STARTS_WITH_QUANTITY.match(i.ingredient_name) for i in ingredients)
    )


def _is_on_a_grocery_list(recipe):
    # Grocery list items cascade-delete with the ingredient row they point at
    return (
        db.session.query(GroceryListItem.id)
        .join(RecipeIngredient)
        .filter(RecipeIngredient.recipe_id == recipe.id)
        .first()
        is not None
    )


def _describe(ingredient):
    return f"{format_quantity(ingredient.quantity)} {ingredient.measurement} {ingredient.ingredient_name}"


def reparse(apply=False):
    with app.app_context():
        recipes = [r for r in Recipe.query.order_by(Recipe.id).all() if _needs_reparse(r)]
        print(f"{len(recipes)} recipe(s) look unparsed\n")

        updated = skipped = 0
        for recipe in recipes:
            print(f"#{recipe.id} {recipe.name}")
            if _is_on_a_grocery_list(recipe):
                print("  skipped: ingredients are referenced by a grocery list\n")
                skipped += 1
                continue

            lines = [i.ingredient_name for i in recipe.recipe_ingredients]
            new_ingredients = Recipe.build_ingredients("\n".join(lines))
            if not new_ingredients:
                print("  skipped: parsing returned nothing\n")
                skipped += 1
                continue

            for line in lines:
                print(f"  - {line}")
            for ingredient in new_ingredients:
                print(f"  + {_describe(ingredient)}")
            print()

            if apply:
                recipe.recipe_ingredients = new_ingredients
                db.session.commit()
            updated += 1

        verb = "Updated" if apply else "Would update"
        print(f"{verb} {updated} recipe(s), skipped {skipped}")
        if not apply:
            print("Dry run only. Re-run with --apply to write changes.")


if __name__ == "__main__":
    reparse(apply="--apply" in sys.argv)
