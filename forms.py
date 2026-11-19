"""
Flask-WTF forms. CSRF protection is automatic via FlaskForm.hidden_tag().
"""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, RadioField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length

from models import DEFAULT_UNIT, UNIT_CHOICES


def _strip(value):
    # Runs before validators, so a trailing space from phone autocomplete
    # doesn't fail the Email() check.
    return value.strip() if isinstance(value, str) else value


class SignupForm(FlaskForm):
    name = StringField(
        "Name",
        filters=[_strip],
        validators=[DataRequired(message="Please enter your name."), Length(min=1, max=120)],
        render_kw={"autocomplete": "name", "autofocus": True, "placeholder": "Your name"},
    )
    email = StringField(
        "Email",
        filters=[_strip],
        validators=[
            DataRequired(message="Email is required."),
            Email(message="That doesn't look like a valid email."),
            Length(max=255),
        ],
        render_kw={"autocomplete": "email", "inputmode": "email", "placeholder": "you@example.com"},
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
            Length(min=8, max=128, message="Use at least 8 characters."),
        ],
        render_kw={"autocomplete": "new-password", "placeholder": "At least 8 characters"},
    )
    unit_pref = RadioField(
        "Weights in",
        choices=[(u, u) for u in UNIT_CHOICES],
        default=DEFAULT_UNIT,
        validators=[DataRequired(message="Pick lb or kg.")],
    )
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        filters=[_strip],
        validators=[
            DataRequired(message="Email is required."),
            Email(message="That doesn't look like a valid email."),
        ],
        render_kw={"autocomplete": "email", "inputmode": "email", "autofocus": True,
                   "placeholder": "you@example.com"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password is required.")],
        render_kw={"autocomplete": "current-password", "placeholder": "Your password"},
    )
    # On by default because this is a phone-first app; uncheck on shared devices.
    remember = BooleanField("Keep me signed in", default=True)
    submit = SubmitField("Sign in")
