from flask_wtf import FlaskForm
from wtforms import TextAreaField, StringField, PasswordField
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


class AddRecipeForm(FlaskForm):
    """Form to add recipe"""

    name = StringField("Recipe Name", validators=[DataRequired()])
    ingredients_text = TextAreaField(
        "Paste Ingredients Section", validators=[DataRequired()]
    )
    url = StringField("Recipe URL", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
