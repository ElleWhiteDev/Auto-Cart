"""
Recipe management routes blueprint.

Handles recipe CRUD operations, ingredient management, and recipe extraction.
"""

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    g,
    jsonify,
    session,
)
from werkzeug.wrappers import Response

from extensions import db, limiter
from models import Recipe, RecipeIngredient, GroceryList, GroceryListItem
from forms import AddRecipeForm
from utils import (
    require_login,
    CURR_GROCERY_LIST_KEY,
    parse_quantity_string,
    get_est_now,
    parse_simple_ingredient,
)
from logging_config import logger
from recipe_scraper import scrape_recipe_data
from typing import Union

recipes_bp = Blueprint("recipes", __name__)


@recipes_bp.route("/add-recipe", methods=["POST"])
@require_login
def add_recipe() -> Response:
    """
    Add a new recipe.

    Returns:
        Redirect to homepage
    """
    form = AddRecipeForm()

    if form.validate_on_submit():
        name = form.name.data
        ingredients_text = form.ingredients_text.data
        url = form.url.data
        notes = form.notes.data
        user_id = g.user.id

        # All recipes are household recipes
        visibility = "household"

        try:
            recipe = Recipe.create_recipe(
                ingredients_text,
                url,
                user_id,
                name,
                notes,
                household_id=g.household.id if g.household else None,
                visibility=visibility,
            )
            db.session.add(recipe)
            db.session.commit()
            flash("Recipe created successfully!", "success")
            return redirect(url_for("main.homepage"))
        except Exception as error:
            db.session.rollback()
            logger.error(f"Recipe creation error: {error}", exc_info=True)
            flash("Error Occurred. Please try again", "danger")
            return redirect(url_for("main.homepage"))
    else:
        logger.warning(f"Form validation failed: {form.errors}")
        flash("Form validation failed. Please check your input.", "danger")

    return redirect(url_for("main.homepage"))


@recipes_bp.route("/recipe/<int:recipe_id>", methods=["GET", "POST"])
def view_recipe(recipe_id: int) -> Union[str, Response]:
    """
    View or edit a recipe.

    Args:
        recipe_id: Recipe ID

    Returns:
        Rendered recipe template or redirect to homepage
    """
    recipe = Recipe.query.get_or_404(recipe_id)

    ingredients_text = "\n".join(
        f"{ingr.quantity} {ingr.measurement} {ingr.ingredient_name}"
        for ingr in recipe.recipe_ingredients
    )

    form = AddRecipeForm(obj=recipe, ingredients_text=ingredients_text)

    if form.validate_on_submit():
        recipe.name = form.name.data
        recipe.url = form.url.data
        recipe.notes = form.notes.data

        # Delete existing ingredients
        for ingredient in recipe.recipe_ingredients:
            db.session.delete(ingredient)

        # Parse and add new ingredients
        ingredients_text = form.ingredients_text.data
        parsed_ingredients = Recipe.parse_ingredients(ingredients_text)

        for ingredient_data in parsed_ingredients:
            ingredient_name = (
                ingredient_data.get("ingredient_name")
                or ingredient_data.get("name")
                or ""
            ).strip()
            if not ingredient_name:
                # Skip invalid model output instead of violating NOT NULL constraint.
                continue

            ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                quantity=ingredient_data.get("quantity"),
                measurement=ingredient_data.get("measurement"),
                ingredient_name=ingredient_name[:40],
            )
            db.session.add(ingredient)

        try:
            db.session.commit()
            flash("Recipe updated successfully!", "success")
            return redirect(url_for("auth.profile"))
        except Exception as error:
            db.session.rollback()
            logger.error(f"Recipe update error: {error}", exc_info=True)
            flash("Error occurred. Please try again", "danger")

    return render_template("recipe.html", recipe=recipe, form=form)


@recipes_bp.route("/recipe/<int:recipe_id>/delete", methods=["POST"])
@require_login
def delete_recipe(recipe_id: int) -> Response:
    """
    Delete a recipe.

    Args:
        recipe_id: Recipe ID

    Returns:
        Redirect to profile page
    """
    recipe = Recipe.query.get_or_404(recipe_id)

    if recipe.user_id != g.user.id:
        flash("Unauthorized", "danger")
        return redirect(url_for("auth.profile"))

    db.session.delete(recipe)
    db.session.commit()
    flash("Recipe deleted successfully!", "success")
    return redirect(url_for("auth.profile"))


@recipes_bp.route("/extract-recipe-form", methods=["POST"])
@require_login
def extract_recipe_form() -> tuple[dict, int]:
    """
    Extract recipe data from URL using web scraping.

    Returns:
        JSON response with recipe data
    """
    url = request.form.get("url")

    if not url:
        return jsonify(
            {"success": False, "error": "URL is required for recipe extraction"}
        ), 400

    recipe_data = scrape_recipe_data(url)

    if recipe_data:
        return jsonify({"success": True, "data": recipe_data})
    else:
        return jsonify(
            {
                "success": False,
                "error": "Failed to extract recipe. Please try entering manually.",
            }
        ), 400


@recipes_bp.route("/standardize-ingredients", methods=["POST"])
@require_login
def standardize_ingredients() -> tuple[dict, int]:
    """
    Standardize ingredients using OpenAI.

    Returns:
        JSON response with standardized ingredients
    """
    ingredients_text = request.form.get("ingredients_text")

    if not ingredients_text:
        return jsonify({"success": False, "error": "Ingredients text is required"}), 400

    try:
        standardized_ingredients = Recipe.clean_ingredients_with_openai(
            ingredients_text
        )

        return jsonify(
            {
                "success": True,
                "data": {"standardized_ingredients": standardized_ingredients},
            }
        )

    except Exception as e:
        logger.error(f"Error standardizing ingredients: {e}", exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "Failed to standardize ingredients. Please try again.",
            }
        ), 500


@recipes_bp.route("/add_manual_ingredient", methods=["POST"])
@require_login
def add_manual_ingredient() -> tuple[dict, int]:
    """
    Add a manually entered ingredient to the grocery list.

    Returns:
        JSON response consumed by the client script
    """
    ingredient_text = request.form.get("ingredient_text", "").strip()

    if not ingredient_text:
        return jsonify({"success": False, "error": "Please enter an ingredient"}), 400

    try:
        parsed_ingredients = Recipe.parse_ingredients(ingredient_text)
        if not parsed_ingredients:
            parsed_ingredients = parse_simple_ingredient(ingredient_text)

        if not parsed_ingredients:
            return (
                jsonify({"success": False, "error": 'Could not parse ingredient. Please use format like "2 cups flour" or just "pickles"'}),
                400,
            )

        grocery_list = g.grocery_list
        if not grocery_list and g.household:
            grocery_list = GroceryList(
                household_id=g.household.id,
                user_id=g.user.id,
                created_by_user_id=g.user.id,
                name="Household Grocery List",
                status="planning",
            )
            db.session.add(grocery_list)
            db.session.commit()
            session[CURR_GROCERY_LIST_KEY] = grocery_list.id
            g.grocery_list = grocery_list

        if not grocery_list:
            return (
                jsonify({"success": False, "error": "Unable to determine a grocery list for this household"}),
                500,
            )

        added_count = 0
        for ingredient_data in parsed_ingredients:
            quantity = parse_quantity_string(str(ingredient_data.get("quantity") or ""))
            if quantity is None:
                quantity = 1.0

            measurement = ingredient_data.get("measurement") or "unit"
            ingredient_name = (
                ingredient_data.get("ingredient_name")
                or ingredient_data.get("name")
                or ingredient_text
            )

            recipe_ingredient = RecipeIngredient(
                ingredient_name=ingredient_name,
                quantity=quantity,
                measurement=measurement,
            )
            db.session.add(recipe_ingredient)
            db.session.flush()

            grocery_list_item = GroceryListItem(
                grocery_list_id=grocery_list.id,
                recipe_ingredient_id=recipe_ingredient.id,
                added_by_user_id=g.user.id,
            )
            db.session.add(grocery_list_item)
            added_count += 1

        grocery_list.last_modified_by_user_id = g.user.id
        grocery_list.last_modified_at = get_est_now()

        db.session.commit()
        return (
            jsonify(
                {"success": True, "message": f"Added {added_count} ingredient{'s' if added_count != 1 else ''} to the list."}
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding manual ingredient: {e}", exc_info=True)
        return (
            jsonify({"success": False, "error": "Error adding ingredient. Please try again."}),
            500,
        )

@recipes_bp.route("/delete_ingredient", methods=["POST"])
@require_login
def delete_ingredient() -> tuple[dict, int]:
    """
    Delete a specific ingredient from the grocery list.

    Returns:
        JSON response
    """
    ingredient_id = request.form.get("ingredient_id")

    if not ingredient_id:
        return jsonify({"success": False, "error": "Invalid ingredient"}), 400

    ingredient = RecipeIngredient.query.get(ingredient_id)

    if not ingredient:
        return jsonify({"success": False, "error": "Ingredient not found"}), 404

    try:
        # Remove linked grocery list item first so foreign key constraint stays intact.
        if g.grocery_list:
            grocery_list_item = GroceryListItem.query.filter_by(
                grocery_list_id=g.grocery_list.id, recipe_ingredient_id=ingredient.id
            ).first()
            if grocery_list_item:
                db.session.delete(grocery_list_item)

        db.session.delete(ingredient)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting ingredient: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to delete ingredient"}), 500
