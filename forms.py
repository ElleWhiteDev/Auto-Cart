from flask_wtf import FlaskForm
from wtforms import TextAreaField, StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Email, Optional, Length, EqualTo


class UserAddForm(FlaskForm):
    """Form for adding users"""

    username = StringField("Username", validators=[DataRequired()])
    email = StringField("E-mail", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[Length(min=6, max=20)])


class LoginForm(FlaskForm):
    """Login form"""

    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[Length(min=6, max=20)])


class UpdatePasswordForm(FlaskForm):
    """Form to change password"""

    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField(
        "New Password",
        validators=[DataRequired(), EqualTo("confirm", message="Passwords must match")],
    )
    confirm = PasswordField("Repeat New Password")


class UpdateEmailForm(FlaskForm):
    """Form to change email"""

    email = StringField("New E-mail", validators=[DataRequired(), Email()])
    password = PasswordField("Current Password", validators=[DataRequired()])


class UpdateUsernameForm(FlaskForm):
    """Form to change username"""

    username = StringField(
        "New Username", validators=[DataRequired(), Length(min=3, max=20)]
    )
    password = PasswordField("Current Password", validators=[DataRequired()])


class AddRecipeForm(FlaskForm):
    """Form to add recipe"""

    name = StringField("Recipe Name", validators=[DataRequired()])
    ingredients_text = TextAreaField(
        "Paste Ingredients Section", validators=[DataRequired()]
    )
    url = StringField("Recipe URL", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])


class AlexaSettingsForm(FlaskForm):
    """Form for updating Alexa integration settings for a user."""

    alexa_access_token = StringField(
        "Alexa Access Token",
        validators=[Optional(), Length(max=255)],
    )

    # Populated at runtime with the user's accessible grocery lists
    default_grocery_list_id = SelectField(
        "Default Grocery List for Alexa",
        coerce=int,
        validators=[Optional()],
    )


class RequestPasswordResetForm(FlaskForm):
    """Form to request password reset"""

    email = StringField("Email", validators=[DataRequired(), Email()])


class ResetPasswordForm(FlaskForm):
    """Form to reset password with token"""

    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=6, max=20),
            EqualTo("confirm", message="Passwords must match"),
        ],
    )
    confirm = PasswordField("Confirm New Password", validators=[DataRequired()])
