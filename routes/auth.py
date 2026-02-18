"""
Authentication routes blueprint.

Handles user registration, login, logout, password management, and profile updates.
"""

from typing import Tuple, Optional, Union
from datetime import datetime
import pytz
from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers import Response
from flask_limiter.errors import RateLimitExceeded

from extensions import db, bcrypt, mail, limiter
from models import User
from forms import (
    UserAddForm,
    LoginForm,
    UpdatePasswordForm,
    UpdateEmailForm,
    UpdateUsernameForm,
    RequestPasswordResetForm,
    ResetPasswordForm,
)
from utils import require_login, do_login, do_logout, send_generic_invitation_email, get_est_now
from constants import FlashCategory, DEFAULT_TIMEZONE
from logging_config import logger

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def register() -> Union[str, Response]:
    """
    Handle user registration.

    Rate limited to 5 registrations per hour per IP to prevent abuse.

    Returns:
        Rendered registration template or redirect to household setup
    """
    form = UserAddForm()

    if form.validate_on_submit():
        user = User.signup(
            username=form.username.data.strip().capitalize(),
            password=form.password.data,
            email=form.email.data.strip(),
        )

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            if "users_email_key" in str(error.orig):
                flash("Email already taken", "danger")
            elif "users_username_key" in str(error.orig):
                flash("Username already taken", "danger")
            else:
                flash("An error occurred. Please try again.", "danger")
            return render_template("register.html", form=form)

        do_login(user)
        flash("Welcome! Please create or join a household to get started.", "info")
        return redirect(url_for("main.household_setup"))

    return render_template("register.html", form=form)


@auth_bp.errorhandler(RateLimitExceeded)
def handle_rate_limit(error: RateLimitExceeded) -> Response:
    """Show a friendly reset time when a rate limit triggers."""
    reset_at = getattr(error, "reset_at", None) or datetime.utcnow()
    if reset_at.tzinfo is None:
        reset_at = pytz.utc.localize(reset_at)
    local_zone = pytz.timezone(DEFAULT_TIMEZONE)
    reset_local = reset_at.astimezone(local_zone)
    reset_str = reset_local.strftime("%I:%M %p")
    flash(
        f"You've hit the rate limit. Please try again after {reset_str} {local_zone.zone}.",
        FlashCategory.WARNING,
    )
    return redirect(request.referrer or url_for("auth.register"))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login() -> Union[str, Response]:
    """
    Handle user login.

    Rate limited to 10 attempts per minute to prevent brute force attacks.

    Returns:
        Rendered login template or redirect to homepage
    """
    form = LoginForm()

    if form.validate_on_submit():
        user = User.authenticate(
            form.username.data.strip().capitalize(), form.password.data
        )

        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", "success")
            return redirect(url_for("main.homepage"))

        flash("Invalid credentials.", "danger")

    return render_template("login.html", form=form)


@auth_bp.route("/logout")
def logout() -> Response:
    """
    Handle user logout.

    Returns:
        Redirect to login page
    """
    do_logout()
    flash("Successfully logged out", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@require_login
def profile() -> Union[str, Response]:
    """
    Display user profile page and handle Alexa settings updates.

    Returns:
        Rendered profile template or redirect
    """
    from forms import AlexaSettingsForm
    from models import GroceryList, HouseholdMember

    alexa_form = AlexaSettingsForm()

    # Build list of grocery lists the user can use for Alexa
    accessible_lists = []

    # Household-scoped lists for households the user belongs to
    memberships = HouseholdMember.query.filter_by(user_id=g.user.id).all()
    household_ids = [m.household_id for m in memberships if m.household_id]

    if household_ids:
        household_lists = (
            GroceryList.query.filter(GroceryList.household_id.in_(household_ids))
            .order_by(GroceryList.name.asc())
            .all()
        )
        accessible_lists.extend(household_lists)

    # Build choices for the SelectField
    choices = [(0, "-- None (Alexa will create a new list) --")]
    for gl in accessible_lists:
        label = gl.name
        if gl.household_id:
            from models import Household

            household = Household.query.get(gl.household_id)
            if household:
                label = f"{gl.name} ({household.name})"
        choices.append((gl.id, label))

    alexa_form.default_grocery_list_id.choices = choices

    if alexa_form.validate_on_submit():
        # Update access token (allow clearing)
        token_val = (alexa_form.alexa_access_token.data or "").strip()
        g.user.alexa_access_token = token_val or None

        # Update default grocery list selection
        selected_id = alexa_form.default_grocery_list_id.data

        if selected_id == 0:
            g.user.alexa_default_grocery_list_id = None
        else:
            # Ensure the selected list is one of the accessible lists
            valid_ids = {gl.id for gl in accessible_lists}
            if selected_id not in valid_ids:
                flash("Invalid grocery list selection for Alexa.", "danger")
                return redirect(url_for("auth.profile"))
            g.user.alexa_default_grocery_list_id = selected_id

        try:
            db.session.commit()
            flash("Alexa settings updated!", "success")
        except Exception as e:
            db.session.rollback()
            flash("Error saving Alexa settings", "danger")

        return redirect(url_for("auth.profile"))

    # Pre-populate form fields on GET
    if request.method == "GET":
        alexa_form.alexa_access_token.data = g.user.alexa_access_token or ""
        if g.user.alexa_default_grocery_list_id:
            alexa_form.default_grocery_list_id.data = (
                g.user.alexa_default_grocery_list_id
            )
        else:
            alexa_form.default_grocery_list_id.data = 0

    return render_template("profile.html", alexa_form=alexa_form)


@auth_bp.route("/delete-account", methods=["POST"])
@require_login
def delete_account() -> Response:
    """
    Delete user account.

    Returns:
        Redirect to login page
    """
    user = g.user
    do_logout()
    db.session.delete(user)
    db.session.commit()
    flash("Account deleted successfully", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/update-password", methods=["GET", "POST"])
@require_login
def update_password() -> Union[str, Response]:
    """
    Handle password update.

    Returns:
        Rendered password update template or redirect to profile
    """
    form = UpdatePasswordForm()

    if form.validate_on_submit():
        try:
            g.user.change_password(
                form.current_password.data, form.new_password.data, form.confirm.data
            )
            db.session.commit()
            flash("Password updated successfully!", "success")
            return redirect(url_for("auth.profile"))
        except ValueError as e:
            flash(str(e), "danger")

    return render_template("update_password.html", form=form)


@auth_bp.route("/update-email", methods=["GET", "POST"])
@require_login
def update_email() -> Union[str, Response]:
    """
    Handle email update.

    Returns:
        Rendered email update template or redirect to profile
    """
    form = UpdateEmailForm()

    if form.validate_on_submit():
        if not bcrypt.check_password_hash(g.user.password, form.password.data):
            flash("Incorrect password", "danger")
            return render_template("update_email.html", form=form)

        try:
            g.user.email = form.email.data.strip()
            db.session.commit()
            flash("Email updated successfully!", "success")
            return redirect(url_for("auth.profile"))
        except IntegrityError:
            db.session.rollback()
            flash("Email already in use", "danger")

    return render_template("update_email.html", form=form)


@auth_bp.route("/update-username", methods=["GET", "POST"])
@require_login
def update_username() -> Union[str, Response]:
    """
    Handle username update.

    Returns:
        Rendered username update template or redirect to profile
    """
    form = UpdateUsernameForm()

    if form.validate_on_submit():
        if not bcrypt.check_password_hash(g.user.password, form.password.data):
            flash("Incorrect password", "danger")
            return render_template("update_username.html", form=form)

        try:
            g.user.username = form.username.data.strip().capitalize()
            db.session.commit()
            flash("Username updated successfully!", "success")
            return redirect(url_for("auth.profile"))
        except IntegrityError:
            db.session.rollback()
            flash("Username already taken", "danger")

    return render_template("update_username.html", form=form)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3 per hour")
def forgot_password() -> Union[str, Response]:
    """
    Handle password reset request.

    Rate limited to 3 requests per hour to prevent abuse.

    Returns:
        Rendered forgot password template or redirect to login
    """
    form = RequestPasswordResetForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip()).first()

        if user:
            # Generate reset token
            if user.reset_token and user.reset_token_expiry and get_est_now() < user.reset_token_expiry:
                expires_at = user.reset_token_expiry.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
                flash(
                    f"A reset link was already sent—please check your email. Link expires at {expires_at.strftime('%I:%M %p')} {DEFAULT_TIMEZONE}.",
                    FlashCategory.INFO,
                )
                return redirect(url_for("auth.login"))

            user.generate_password_reset_token()
            db.session.commit()

            # Send reset email (implementation in models.py)
            try:
                user.send_password_reset_email(mail)
                flash("Password reset instructions sent to your email", "info")
            except Exception as e:
                logger.error(f"Error sending password reset email: {e}", exc_info=True)
                flash("Error sending email. Please try again later.", "danger")
        else:
            # Don't reveal if email exists (security best practice)
            flash(
                "If that email exists, password reset instructions have been sent",
                "info",
            )

        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def reset_password(token: str) -> Union[str, Response]:
    """
    Handle password reset with token.

    Args:
        token: Password reset token

    Returns:
        Rendered reset password template or redirect to login
    """
    user = User.verify_password_reset_token(token)

    if not user:
        flash("Invalid or expired reset link", "danger")
        return redirect(url_for("auth.login"))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        user.password = bcrypt.generate_password_hash(form.password.data).decode(
            "utf-8"
        )
        user.password_reset_token = None
        user.password_reset_expires = None
        db.session.commit()

        flash("Password reset successfully! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", form=form, token=token)


@auth_bp.route("/send-invite", methods=["POST"])
def send_invite_email() -> Response:
    """
    Send a generic invitation email to someone.

    Returns:
        Redirect to registration page with success/error message
    """
    invite_email = request.form.get("invite_email", "").strip()
    invite_name = request.form.get("invite_name", "").strip()
    sender_name = request.form.get("sender_name", "").strip()

    if not invite_email:
        flash("Please provide an email address", "danger")
        return redirect(url_for("auth.register"))

    try:
        send_generic_invitation_email(invite_email, invite_name, sender_name)
        flash(f"✅ Invitation sent to {invite_email}!", "success")
    except Exception as e:
        logger.error(f"Failed to send invitation email: {e}", exc_info=True)
        flash("❌ Failed to send invitation email. Please try again.", "danger")

    return redirect(url_for("auth.register"))
