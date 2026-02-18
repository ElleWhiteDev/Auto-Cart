"""
Main routes blueprint.

Handles homepage, household management, and general application routes.
"""

from typing import Optional, Union
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    g,
    session,
)
from werkzeug.wrappers import Response

from extensions import db
from models import User, Recipe, GroceryList, Household, HouseholdMember
from forms import AddRecipeForm
from utils import require_login, initialize_session_defaults
from logging_config import logger

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def homepage() -> Union[str, Response]:
    """
    Show homepage with recipes and grocery list.

    Requires login and household membership.

    Returns:
        Rendered homepage template or redirect
    """
    # Redirect to login if not authenticated
    if not g.user:
        return redirect(url_for("auth.login"))

    # If user has no household, redirect to household creation
    if not g.household:
        return redirect(url_for("main.create_household"))

    initialize_session_defaults()

    # Get household recipes (both personal and shared)
    recipes = Recipe.query.filter(
        (Recipe.household_id == g.household.id)
        | ((Recipe.user_id == g.user.id) & (Recipe.household_id.is_(None)))
    ).all()

    selected_recipe_ids = session.get("selected_recipe_ids", [])
    logger.debug(f"Selected recipe IDs: {selected_recipe_ids}")
    logger.debug(f"User recipe IDs: {[recipe.id for recipe in recipes]}")

    # Get household members for email selection
    household_members = HouseholdMember.query.filter_by(
        household_id=g.household.id
    ).all()
    household_users = [m.user for m in household_members]

    # Get all household grocery lists
    all_grocery_lists = (
        GroceryList.query.filter_by(household_id=g.household.id)
        .order_by(GroceryList.last_modified_at.desc())
        .all()
    )

    form = AddRecipeForm()
    return render_template(
        "index.html",
        form=form,
        recipes=recipes,
        selected_recipe_ids=selected_recipe_ids,
        all_users=household_users,
        all_grocery_lists=all_grocery_lists,
    )


@main_bp.route("/household/setup", methods=["GET", "POST"])
@require_login
def household_setup() -> Union[str, Response]:
    """
    Setup page for new users to create or join a household.

    Returns:
        Rendered household setup template or redirect to homepage
    """
    # If user already has a household, redirect to homepage
    if g.household:
        return redirect(url_for("main.homepage"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            household_name = request.form.get("household_name", "").strip()

            if not household_name:
                flash("Please enter a household name", "danger")
                return render_template("household_setup.html")

            # Create new household
            household = Household(name=household_name)
            db.session.add(household)
            db.session.flush()  # Get household ID

            # Add user as owner
            member = HouseholdMember(
                household_id=household.id, user_id=g.user.id, role="owner"
            )
            db.session.add(member)
            db.session.commit()

            flash(f'Household "{household_name}" created successfully!', "success")
            return redirect(url_for("main.homepage"))

        elif action == "join":
            invite_code = request.form.get("invite_code", "").strip()

            if not invite_code:
                flash("Please enter an invite code", "danger")
                return render_template("household_setup.html")

            # Find household by invite code (implementation needed)
            flash("Invite code feature coming soon!", "info")
            return render_template("household_setup.html")

    return render_template("household_setup.html")


@main_bp.route("/household/create", methods=["GET", "POST"])
@require_login
def create_household() -> Union[str, Response]:
    """
    Create a new household.

    Returns:
        Rendered create household template or redirect to homepage
    """
    if request.method == "POST":
        household_name = request.form.get("household_name", "").strip()

        if not household_name:
            flash("Please enter a household name", "danger")
            return render_template("create_household.html")

        # Create new household
        household = Household(name=household_name)
        db.session.add(household)
        db.session.flush()

        # Add user as owner
        member = HouseholdMember(
            household_id=household.id, user_id=g.user.id, role="owner"
        )
        db.session.add(member)
        db.session.commit()

        flash(f'Household "{household_name}" created successfully!', "success")
        return redirect(url_for("main.homepage"))

    return render_template("create_household.html")
