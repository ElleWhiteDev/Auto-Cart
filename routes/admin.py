"""
Administrative routes blueprint.

Handles admin authentication and user management.
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
)
from werkzeug.wrappers import Response

from extensions import db, bcrypt, mail
from models import User, HouseholdMember, Household, Recipe, GroceryList, MealPlanEntry
from utils import require_admin, do_login
from logging_config import logger
from typing import Union, Tuple, Dict, Any

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login() -> Union[str, Response]:
    """
    Admin login page.

    Returns:
        Rendered admin login template or redirect to dashboard
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            if user.is_admin:
                do_login(user)
                flash("Admin login successful!", "success")
                return redirect(url_for("admin.admin_dashboard"))
            else:
                flash("Access denied. Admin privileges required.", "danger")
        else:
            flash("Invalid username or password", "danger")

    return render_template("admin_login.html")


@admin_bp.route("/dashboard")
@require_admin
def admin_dashboard() -> str:
    """
    Admin dashboard showing all users and households.

    Returns:
        Rendered admin dashboard template
    """
    users = User.query.order_by(User.last_activity.desc().nullslast()).all()
    households = Household.query.order_by(Household.created_at.desc()).all()

    # Get household stats
    household_stats = []
    for household in households:
        members = HouseholdMember.query.filter_by(household_id=household.id).all()
        owner = next((m.user for m in members if m.role == "owner"), None)
        recipes_count = Recipe.query.filter_by(household_id=household.id).count()
        lists_count = GroceryList.query.filter_by(household_id=household.id).count()
        meals_count = MealPlanEntry.query.filter_by(household_id=household.id).count()
        email_enabled_count = sum(1 for m in members if m.receive_meal_plan_emails)
        chef_email_enabled_count = sum(
            1 for m in members if m.receive_chef_assignment_emails
        )

        household_stats.append(
            {
                "household": household,
                "owner": owner,
                "members_count": len(members),
                "email_enabled_count": email_enabled_count,
                "chef_email_enabled_count": chef_email_enabled_count,
                "recipes_count": recipes_count,
                "lists_count": lists_count,
                "meals_count": meals_count,
            }
        )

    return render_template(
        "admin_dashboard.html", users=users, household_stats=household_stats
    )


@admin_bp.route("/delete-user/<int:user_id>", methods=["POST"])
@require_admin
def admin_delete_user(user_id: int) -> Response:
    """
    Delete a user from the admin panel.

    Args:
        user_id: User ID to delete

    Returns:
        Redirect to admin dashboard
    """
    if user_id == g.user.id:
        flash("You cannot delete your own admin account", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    user = User.query.get_or_404(user_id)
    username = user.username

    try:
        # Delete household memberships first to avoid foreign key constraint issues
        HouseholdMember.query.filter_by(user_id=user_id).delete()

        # Now delete the user
        db.session.delete(user)
        db.session.commit()
        flash(f'User "{username}" deleted successfully', "success")
        logger.info(f"Admin {g.user.username} deleted user {username} (ID: {user_id})")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {e}", exc_info=True)
        flash("Error deleting user. Please try again.", "danger")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/delete-household/<int:household_id>", methods=["POST"])
@require_admin
def admin_delete_household(household_id: int) -> Response:
    """
    Delete a household from the admin panel.

    Args:
        household_id: Household ID to delete

    Returns:
        Redirect to admin dashboard
    """
    household = Household.query.get_or_404(household_id)
    household_name = household.name

    try:
        logger.info(f"Admin {g.user.username} deleting household: {household_name} (ID: {household_id})")
        members_count = HouseholdMember.query.filter_by(household_id=household_id).count()
        recipes_count = Recipe.query.filter_by(household_id=household_id).count()
        lists_count = GroceryList.query.filter_by(household_id=household_id).count()
        meals_count = MealPlanEntry.query.filter_by(household_id=household_id).count()

        logger.info(
            f"Household stats before delete: {members_count} members, "
            f"{recipes_count} recipes, {lists_count} lists, {meals_count} meals"
        )

        db.session.delete(household)
        db.session.commit()

        flash(
            f'✅ Household "{household_name}" deleted successfully '
            f'(removed {members_count} memberships, {recipes_count} recipes, {lists_count} lists, {meals_count} meals)',
            "success",
        )
        logger.info(f"Successfully deleted household: {household_name}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting household {household_name}: {e}", exc_info=True)
        flash(f'❌ Error deleting household "{household_name}": {str(e)}', "danger")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/toggle-member-email", methods=["POST"])
@require_admin
def admin_toggle_member_email() -> Tuple[Dict[str, Any], int]:
    """
    Toggle email preferences for a household member (AJAX endpoint).

    Returns:
        JSON response with success status or error message
    """
    try:
        data = request.get_json()
        member_id = data.get("member_id")
        email_type = data.get("email_type")  # 'meal_plan' or 'chef'
        enabled = data.get("enabled")

        if member_id is None or email_type is None or enabled is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # Get the household member record
        member = HouseholdMember.query.get(member_id)

        if not member:
            return jsonify({"success": False, "error": "Member not found"}), 404

        # Update the appropriate preference
        if email_type == "meal_plan":
            member.receive_meal_plan_emails = enabled
            email_type_name = "meal plan"
        elif email_type == "chef":
            member.receive_chef_assignment_emails = enabled
            email_type_name = "chef assignment"
        else:
            return jsonify({"success": False, "error": "Invalid email type"}), 400

        db.session.commit()

        logger.info(
            f"Admin {g.user.username} {'enabled' if enabled else 'disabled'} {email_type_name} emails "
            f"for user {member.user.username} in household {member.household_id}"
        )

        return jsonify({"success": True}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling member email preference: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/update-user-email", methods=["POST"])
@require_admin
def admin_update_user_email() -> Tuple[Dict[str, Any], int]:
    """
    Update a user's email from the admin panel (AJAX endpoint).

    Returns:
        JSON response with success status and updated email or error message
    """
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        new_email = data.get("email", "").strip()

        if not user_id or not new_email:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # Validate email format
        if "@" not in new_email or "." not in new_email:
            return jsonify({"success": False, "error": "Invalid email format"}), 400

        # Get the user
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Check if email is already in use by another user
        existing_user = User.query.filter_by(email=new_email).first()
        if existing_user and existing_user.id != user_id:
            return jsonify({"success": False, "error": "Email already in use"}), 400

        old_email = user.email
        user.email = new_email
        db.session.commit()

        logger.info(
            f"Admin {g.user.username} updated email for user {user.username} "
            f"from {old_email} to {new_email}"
        )

        return jsonify({"success": True, "email": new_email}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user email: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/send-feature-announcement", methods=["POST"])
@require_admin
def send_feature_announcement() -> Response:
    """
    Send the latest feature announcement email to all registered users.

    Returns:
        Redirect to admin dashboard
    """
    try:
        # Get all users
        users = User.query.all()

        if not users:
            flash("No users found to send emails to", "warning")
            return redirect(url_for("admin.admin_dashboard"))

        # Send email to each user
        sent_count = 0
        failed_count = 0

        for user in users:
            try:
                send_feature_announcement_email(user.email, user.username)
                sent_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to send feature announcement to {user.email}: {e}"
                )
                failed_count += 1

        if sent_count > 0:
            flash(f"✅ Feature announcement sent to {sent_count} user(s)!", "success")
        if failed_count > 0:
            flash(
                f"⚠️ Failed to send to {failed_count} user(s). Check logs for details.",
                "warning",
            )

        logger.info(
            f"Feature announcement sent to {sent_count} users, {failed_count} failed"
        )

    except Exception as e:
        logger.error(f"Error sending feature announcements: {e}", exc_info=True)
        flash(f"❌ Error sending announcements: {str(e)}", "danger")

    return redirect(url_for("admin.admin_dashboard"))


def send_feature_announcement_email(recipient_email: str, recipient_name: str) -> None:
    """
    Send feature announcement email to a user.

    Args:
        recipient_email: Recipient's email address
        recipient_name: Recipient's name
    """
    from flask_mail import Message
    from flask import render_template, request

    # Build URLs
    base_url = request.url_root.rstrip("/")
    meal_plan_url = f"{base_url}/meal-plan"
    homepage_url = f"{base_url}/"
    profile_url = f"{base_url}/profile"

    subject = "🎉 New Feature: Similar Recipes - Smart Meal Planning with AI!"

    # Render HTML email from template
    html_body = render_template(
        "feature_announcement_email.html",
        recipient_name=recipient_name,
        meal_plan_url=meal_plan_url,
        homepage_url=homepage_url,
        profile_url=profile_url,
    )

    # Create plain text version
    text_body = f"""
Hey {recipient_name}! 👋

We're excited to share a brand new feature that's going to make meal planning even easier: Similar Recipes!

🎯 What's New?

When you're planning your meals for the week, Auto-Cart now suggests recipes that share ingredients with what you've already selected. This means:

• Less food waste - use up ingredients across multiple meals
• Smarter shopping - fewer items to buy
• More variety - discover recipes you might not have considered

🚀 How It Works:

1. Add a recipe to your meal plan
2. Click "Find Similar Recipes"
3. See AI-powered suggestions ranked by ingredient overlap
4. Add matching recipes with one click!

Try it out: {meal_plan_url}

Happy cooking!
The Auto-Cart Team

---
You're receiving this because you have an Auto-Cart account.
Visit Auto-Cart: {homepage_url}
Manage Your Profile: {profile_url}
    """

    msg = Message(
        subject=subject, recipients=[recipient_email], html=html_body, body=text_body
    )

    mail.send(msg)
    logger.info(f"Feature announcement email sent to {recipient_email}")
