"""
RepWise — Flask app factory and routes.

Phase 0 is the skeleton: config, security guards, SQLite tuning, a landing
page, and /healthz. Auth lands in Phase 1A, the exercise library in 1B.
See PLAN.md for the roadmap.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from flask import Flask, render_template
from sqlalchemy import event, text
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import csrf, db

load_dotenv()

log = logging.getLogger(__name__)

APP_PHASE = "0"

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

    with app.app_context():
        if _is_sqlite_database_url(app.config["SQLALCHEMY_DATABASE_URI"]):
            event.listen(db.engine, "connect", _configure_sqlite_journal_mode)
        db.create_all()

    _register_routes(app)
    return app


def _register_routes(app: Flask) -> None:

    @app.route("/")
    def index():
        return render_template("index.html")

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
