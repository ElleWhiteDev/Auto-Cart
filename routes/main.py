"""
Main routes blueprint.

Handles homepage, household management, and general application routes.
"""

from typing import Optional, Union, Dict, Any, Tuple
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    g,
    session,
    jsonify,
)
from werkzeug.wrappers import Response
from flask_mail import Message

from extensions import db, mail
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


@main_bp.route("/household/settings")
@require_login
def household_settings() -> Union[str, Response]:
    """
    View and manage household settings.

    Returns:
        Rendered household settings template or redirect
    """
    if not g.household:
        return redirect(url_for("main.create_household"))

    members = HouseholdMember.query.filter_by(household_id=g.household.id).all()

    # Get Kroger account user if set
    kroger_user = None
    if g.household.kroger_user_id:
        kroger_user = User.query.get(g.household.kroger_user_id)

    # Get all households the user belongs to for switching
    user_households = g.user.get_households()

    return render_template(
        "household_settings.html",
        household=g.household,
        members=members,
        kroger_user=kroger_user,
        is_owner=(g.household_member.role == "owner"),
        user_households=user_households,
    )


@main_bp.route("/household/invite", methods=["POST"])
@require_login
def invite_household_member() -> Response:
    """
    Invite a user to the household by username.

    Returns:
        Redirect to household settings
    """
    if not g.household or g.household_member.role != "owner":
        flash("Only household owners can invite members", "danger")
        return redirect(url_for("main.household_settings"))

    username = request.form.get("username", "").strip()

    if not username:
        flash("Please enter a username", "danger")
        return redirect(url_for("main.household_settings"))

    # Find user
    user = User.query.filter_by(username=username).first()
    if not user:
        flash(f'User "{username}" not found', "danger")
        return redirect(url_for("main.household_settings"))

    # Check if already a member
    existing = HouseholdMember.query.filter_by(
        household_id=g.household.id, user_id=user.id
    ).first()
    if existing:
        flash(f"{username} is already a member of this household", "warning")
        return redirect(url_for("main.household_settings"))

    # Add as member
    member = HouseholdMember(
        household_id=g.household.id, user_id=user.id, role="member"
    )
    db.session.add(member)
    db.session.commit()

    flash(f"{username} has been added to the household!", "success")
    return redirect(url_for("main.household_settings"))


@main_bp.route("/household/remove-member/<int:user_id>", methods=["POST"])
@require_login
def remove_household_member(user_id: int) -> Response:
    """
    Remove a member from the household.

    Args:
        user_id: User ID to remove

    Returns:
        Redirect to household settings
    """
    if not g.household or g.household_member.role != "owner":
        flash("Only household owners can remove members", "danger")
        return redirect(url_for("main.household_settings"))

    if user_id == g.user.id:
        flash("You cannot remove yourself from the household", "danger")
        return redirect(url_for("main.household_settings"))

    membership = HouseholdMember.query.filter_by(
        household_id=g.household.id, user_id=user_id
    ).first()

    if not membership:
        flash("Member not found", "danger")
        return redirect(url_for("main.household_settings"))

    db.session.delete(membership)
    db.session.commit()

    flash("Member removed successfully", "success")
    return redirect(url_for("main.household_settings"))


@main_bp.route("/household/set-kroger-user/<int:user_id>", methods=["POST"])
@require_login
def set_kroger_user(user_id: int) -> Response:
    """
    Set the household's Kroger account user.

    Args:
        user_id: User ID to set as Kroger account

    Returns:
        Redirect to household settings
    """
    if not g.household or g.household_member.role != "owner":
        flash("Only household owners can set the Kroger account", "danger")
        return redirect(url_for("main.household_settings"))

    # Verify user is a member and has Kroger connected
    membership = HouseholdMember.query.filter_by(
        household_id=g.household.id, user_id=user_id
    ).first()

    if not membership:
        flash("User is not a member of this household", "danger")
        return redirect(url_for("main.household_settings"))

    user = User.query.get(user_id)
    if not user.oauth_token:
        flash("This user has not connected their Kroger account yet", "warning")
        return redirect(url_for("main.household_settings"))

    g.household.kroger_user_id = user_id
    db.session.commit()

    flash(f"Kroger account set to {user.username}", "success")
    return redirect(url_for("main.household_settings"))


@main_bp.route("/household/switch/<int:household_id>")
@require_login
def switch_household(household_id: int) -> Response:
    """
    Switch to a different household.

    Args:
        household_id: Household ID to switch to

    Returns:
        Redirect to homepage
    """
    # Verify user is a member
    membership = HouseholdMember.query.filter_by(
        household_id=household_id, user_id=g.user.id
    ).first()

    if not membership:
        flash("You are not a member of that household", "danger")
        return redirect(url_for("main.homepage"))

    session["household_id"] = household_id
    flash("Switched household successfully", "success")
    return redirect(url_for("main.homepage"))


@main_bp.route("/household/edit-name", methods=["POST"])
@require_login
def edit_household_name() -> Response:
    """
    Edit household name.

    Returns:
        Redirect to household settings
    """
    if not g.household or g.household_member.role != "owner":
        flash("Only household owners can edit the household name", "danger")
        return redirect(url_for("main.household_settings"))

    household_name = request.form.get("household_name", "").strip()

    if not household_name:
        flash("Please enter a household name", "danger")
        return redirect(url_for("main.household_settings"))

    g.household.name = household_name
    db.session.commit()

    flash("Household name updated successfully", "success")
    return redirect(url_for("main.household_settings"))


@main_bp.route("/household/delete", methods=["POST"])
@require_login
def delete_household() -> Response:
    """
    Delete household and all associated data.

    Returns:
        Redirect to household setup
    """
    if not g.household or g.household_member.role != "owner":
        flash("Only household owners can delete the household", "danger")
        return redirect(url_for("main.household_settings"))

    household_id = g.household.id
    household_name = g.household.name

    # Delete household (cascade will handle related records)
    db.session.delete(g.household)
    db.session.commit()

    # Clear session
    session.pop("household_id", None)

    flash(f'Household "{household_name}" has been deleted', "success")
    return redirect(url_for("main.household_setup"))


@main_bp.route("/household/toggle-meal-plan-emails", methods=["POST"])
@require_login
def toggle_meal_plan_emails() -> Tuple[Dict[str, Any], int]:
    """
    Toggle meal plan email notifications for a household member.

    Returns:
        JSON response with success status or error message
    """
    try:
        data = request.get_json()
        member_id = data.get("member_id")
        enabled = data.get("enabled")

        if member_id is None or enabled is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # Get the household member record
        member = HouseholdMember.query.get(member_id)

        if not member:
            return jsonify({"success": False, "error": "Member not found"}), 404

        # Verify the current user is updating their own preference
        if member.user_id != g.user.id:
            return jsonify(
                {
                    "success": False,
                    "error": "You can only update your own email preferences",
                }
            ), 403

        # Update preference
        member.receive_meal_plan_emails = enabled
        db.session.commit()

        logger.info(
            f"User {g.user.username} {'enabled' if enabled else 'disabled'} meal plan emails"
        )

        return jsonify({"success": True}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling meal plan email preference: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/household/toggle-chef-assignment-emails", methods=["POST"])
@require_login
def toggle_chef_assignment_emails() -> Tuple[Dict[str, Any], int]:
    """
    Toggle chef assignment email notifications for a household member.

    Returns:
        JSON response with success status or error message
    """
    try:
        data = request.get_json()
        member_id = data.get("member_id")
        enabled = data.get("enabled")

        if member_id is None or enabled is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # Get the household member record
        member = HouseholdMember.query.get(member_id)

        if not member:
            return jsonify({"success": False, "error": "Member not found"}), 404

        # Verify the current user is updating their own preference
        if member.user_id != g.user.id:
            return jsonify(
                {
                    "success": False,
                    "error": "You can only update your own email preferences",
                }
            ), 403

        # Update preference
        member.receive_chef_assignment_emails = enabled
        db.session.commit()

        logger.info(
            f"User {g.user.username} {'enabled' if enabled else 'disabled'} chef assignment emails"
        )

        return jsonify({"success": True}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(
            f"Error toggling chef assignment email preference: {e}", exc_info=True
        )
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/submit-feedback", methods=["POST"])
@require_login
def submit_feedback() -> Response:
    """
    Handle user feedback submission.

    Returns:
        Redirect to previous page with success/error message
    """
    feedback_type = request.form.get("feedback_type", "").strip()
    message = request.form.get("message", "").strip()

    if not feedback_type or not message:
        flash("Please fill in all fields", "danger")
        return redirect(request.referrer or url_for("main.homepage"))

    try:
        # Send feedback email to admin/support
        admin_email = "ellewhitedev@gmail.com"  # You can move this to config

        msg = Message(
            subject=f"Auto Cart Feedback: {feedback_type.title()}",
            sender="noreply@autocart.com",
            recipients=[admin_email],
        )

        msg.body = f"""
New feedback received from Auto Cart:

User: {g.user.username} ({g.user.email})
Feedback Type: {feedback_type.title()}
Household: {g.household.name if g.household else "None"}

Message:
{message}

---
Submitted at: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        msg.html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 8px;">
        <h2 style="color: #004c91; border-bottom: 2px solid #004c91; padding-bottom: 10px;">
            New Auto Cart Feedback
        </h2>

        <div style="background-color: white; padding: 20px; border-radius: 6px; margin: 20px 0;">
            <p><strong>User:</strong> {g.user.username} ({g.user.email})</p>
            <p><strong>Feedback Type:</strong> <span style="color: #004c91;">{feedback_type.title()}</span></p>
            <p><strong>Household:</strong> {g.household.name if g.household else "None"}</p>
        </div>

        <div style="background-color: white; padding: 20px; border-radius: 6px; margin: 20px 0;">
            <h3 style="color: #004c91; margin-top: 0;">Message:</h3>
            <p style="white-space: pre-wrap;">{message}</p>
        </div>

        <p style="color: #666; font-size: 12px; margin-top: 20px;">
            Submitted at: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </p>
    </div>
</body>
</html>
"""

        mail.send(msg)
        flash("Thank you for your feedback! We'll review it shortly.", "success")
        logger.info(f"Feedback submitted by user {g.user.id}: {feedback_type}")

    except Exception as e:
        logger.error(f"Error sending feedback email: {e}", exc_info=True)
        flash(
            "There was an error submitting your feedback. Please try again later.",
            "danger",
        )

    return redirect(request.referrer or url_for("main.homepage"))
