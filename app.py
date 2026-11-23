"""
RepWise — Flask app factory and routes.

Routes are grouped by feature: public pages, auth, then the signed-in app.
See PLAN.md for the roadmap.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import event, text
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import csrf, db, login_manager
from forms import LoginForm, SignupForm
from models import User
from seed_exercises import seed_exercises

load_dotenv()

log = logging.getLogger(__name__)

APP_PHASE = "1B2"

_PLACEHOLDER_SECRET_KEY = "dev-secret-change-me-in-env"

SQLITE_BUSY_TIMEOUT_SECONDS = 15
SQLITE_JOURNAL_MODE_ENV = "SQLITE_JOURNAL_MODE"
SQLITE_DEFAULT_JOURNAL_MODE = "WAL"
# PythonAnywhere's free tier runs on a network filesystem where WAL sidecar
# files are unreliable, so its deploy sets SQLITE_JOURNAL_MODE=DELETE.
SQLITE_ALLOWED_JOURNAL_MODES = {"WAL", "DELETE"}


def _is_sqlite_database_url(database_url: str) -> bool:
    return database_url.startswith("sqlite:")


def _sqlite_journal_mode() -> str:
    requested = os.environ.get(
        SQLITE_JOURNAL_MODE_ENV, SQLITE_DEFAULT_JOURNAL_MODE,
    ).strip().upper()
    if requested in SQLITE_ALLOWED_JOURNAL_MODES:
        return requested
    return SQLITE_DEFAULT_JOURNAL_MODE


def _configure_sqlite_journal_mode(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA journal_mode={_sqlite_journal_mode()}")
    finally:
        cursor.close()


def _is_production_env() -> bool:
    return os.environ.get("FLASK_ENV", "").lower() == "production"


def _configure_production_cookie_security(app: Flask) -> None:
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=True,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
    )


def create_app() -> Flask:
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get(
        "FLASK_SECRET_KEY", _PLACEHOLDER_SECRET_KEY
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///repwise.sqlite3"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if _is_sqlite_database_url(app.config["SQLALCHEMY_DATABASE_URI"]):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"timeout": SQLITE_BUSY_TIMEOUT_SECONDS},
        }

    if _is_production_env():
        _configure_production_cookie_security(app)
        # A well-known key would make session cookies forgeable and CSRF
        # tokens predictable, so production refuses to boot without a real one.
        if (not app.config["SECRET_KEY"]
                or app.config["SECRET_KEY"] == _PLACEHOLDER_SECRET_KEY):
            raise RuntimeError(
                "FLASK_SECRET_KEY is unset or is the default placeholder, "
                "but FLASK_ENV=production. Refusing to start. Set a real "
                "FLASK_SECRET_KEY in the deploy environment or server-side "
                ".env file, then reload the app."
            )

    # Trust exactly one upstream proxy hop (the host's edge) so
    # request.is_secure and url_for(_external=True) see HTTPS.
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1,
    )

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"

    with app.app_context():
        if _is_sqlite_database_url(app.config["SQLALCHEMY_DATABASE_URI"]):
            event.listen(db.engine, "connect", _configure_sqlite_journal_mode)
        db.create_all()
        # Keeps a deployed library in sync with seed_exercises.py on reload,
        # with no manual step. Idempotent, and a no-op write when unchanged.
        seed_exercises()

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    _register_routes(app)
    return app


def _is_safe_next_url(next_url: str) -> bool:
    r"""
    A `?next=` URL is safe only if it's a same-origin path with no scheme
    and no host:
      - `/today`          → safe
      - `//evil.com`      → unsafe (protocol-relative)
      - `/\evil.com`      → unsafe (browsers normalize \ to /, so this
                            becomes //evil.com even though urlsplit sees
                            an empty netloc)
      - `http://evil`     → unsafe (full URL)
      - `javascript:…`    → unsafe (scheme)
    """
    if not next_url:
        return False
    if "\\" in next_url:
        return False
    parsed = urlsplit(next_url)
    return not parsed.netloc and not parsed.scheme


def _register_routes(app: Flask) -> None:

    # --- Public -------------------------------------------------------------

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("today"))
        return render_template("index.html")

    # --- Auth ---------------------------------------------------------------

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user.is_authenticated:
            return redirect(url_for("today"))

        form = SignupForm()
        if form.validate_on_submit():
            email = form.email.data.strip().lower()
            if User.query.filter_by(email=email).first() is not None:
                flash("An account with that email already exists. Try signing in.", "error")
                return render_template("signup.html", form=form)

            user = User(
                email=email,
                name=form.name.data.strip(),
                unit_pref=form.unit_pref.data,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            login_user(user, remember=True)
            flash(f"Welcome to RepWise, {user.first_name}!", "success")
            return redirect(url_for("today"))

        return render_template("signup.html", form=form)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("today"))

        form = LoginForm()
        if form.validate_on_submit():
            email = form.email.data.strip().lower()
            user = User.query.filter_by(email=email).first()
            if user is None or not user.check_password(form.password.data):
                flash("Invalid email or password.", "error")
                return render_template("login.html", form=form)

            login_user(user, remember=form.remember.data)
            next_url = request.args.get("next")
            if next_url and _is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("today"))

        return render_template("login.html", form=form)

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        flash("You've been signed out.", "info")
        return redirect(url_for("login"))

    # --- Signed-in app ------------------------------------------------------

    @app.route("/today")
    @login_required
    def today():
        return render_template("today.html")

    @app.route("/healthz")
    def healthz():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception as e:
            log.warning("Health check database ping failed: %s", e)
            return {
                "status": "error",
                "phase": APP_PHASE,
                "database": "unavailable",
            }, 503
        return {"status": "ok", "phase": APP_PHASE}


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5002, host="0.0.0.0")
