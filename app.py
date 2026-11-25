"""
RepWise — Flask app factory and routes.

Routes are grouped by feature: public pages, auth, then the signed-in app.
See PLAN.md for the roadmap.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix

import exercise_vocab
from extensions import csrf, db, login_manager
from forms import LoginForm, SignupForm
from models import Exercise, User, Workout
from seed_exercises import seed_exercises

load_dotenv()

log = logging.getLogger(__name__)

APP_PHASE = "1C1"

EXERCISE_SEARCH_MAX_LENGTH = 80

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

    app.jinja_env.filters["tag_label"] = exercise_vocab.label
    app.jinja_env.filters["relative_time"] = _relative_time
    app.jinja_env.globals["difficulty_labels"] = exercise_vocab.DIFFICULTY_LABELS

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


def _relative_time(when: datetime, now: datetime = None) -> str:
    """'just now', '5 min ago', '2 hr ago', 'yesterday', '3 days ago' for a
    naive UTC datetime."""
    seconds = int(((now or datetime.utcnow()) - when).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    return "yesterday" if days == 1 else f"{days} days ago"


def _open_workout_for(user):
    return Workout.query.filter_by(user_id=user.id, finished_at=None).first()


def _get_open_workout_or_404(workout_id: int) -> Workout:
    """404 for someone else's workout too, so ids don't leak existence."""
    workout = db.session.get(Workout, workout_id)
    if workout is None or workout.user_id != current_user.id or not workout.is_open:
        abort(404)
    return workout


def _visible_exercises_query():
    """Global exercises plus the signed-in user's own custom ones."""
    return Exercise.query.filter(db.or_(
        Exercise.owner_user_id.is_(None),
        Exercise.owner_user_id == current_user.id,
    ))


def _exercise_search_text(exercise: Exercise) -> str:
    tags = [exercise.movement_pattern, *exercise.primary_muscles,
            *exercise.secondary_muscles, *exercise.equipment]
    if exercise.is_bodyweight:
        tags.append("bodyweight")
    return " ".join([exercise.name, *tags, *(t.replace("-", " ") for t in tags)]).lower()


def _search_exercises(exercises, query: str):
    """Every word in the query must appear in the name or a tag, so
    'dumbbell chest' narrows rather than widens."""
    words = query.lower().split()
    if not words:
        return list(exercises)
    return [e for e in exercises
            if all(w in _exercise_search_text(e) for w in words)]


def _group_by_pattern(exercises):
    """[(pattern, [exercises sorted by name])] in vocabulary order, empty
    groups omitted."""
    groups = {p: [] for p in exercise_vocab.MOVEMENT_PATTERNS}
    for e in exercises:
        groups.setdefault(e.movement_pattern, []).append(e)
    return [(p, sorted(items, key=lambda e: e.name.lower()))
            for p, items in groups.items() if items]


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
        return render_template("today.html", open_workout=_open_workout_for(current_user))

    @app.route("/workouts/start", methods=["POST"])
    @login_required
    def workout_start():
        workout = _open_workout_for(current_user)
        if workout is None:
            workout = Workout(user_id=current_user.id)
            db.session.add(workout)
            try:
                db.session.commit()
            except IntegrityError:
                # A concurrent Start won the unique-open-workout index.
                db.session.rollback()
                workout = _open_workout_for(current_user)
        return redirect(url_for("workout_active", workout_id=workout.id))

    @app.route("/workouts/<int:workout_id>")
    @login_required
    def workout_active(workout_id: int):
        return render_template("workout.html", workout=_get_open_workout_or_404(workout_id))

    @app.route("/workouts/<int:workout_id>/finish", methods=["POST"])
    @login_required
    def workout_finish(workout_id: int):
        workout = _get_open_workout_or_404(workout_id)
        kept = workout.prune_unlogged()
        if kept == 0:
            db.session.delete(workout)
            db.session.commit()
            flash("Nothing was logged, so the workout was discarded.", "info")
            return redirect(url_for("today"))
        workout.finished_at = datetime.utcnow()
        exercise_count = len(workout.exercises)
        db.session.commit()
        flash(
            f"Workout saved: {exercise_count} exercise{'s' if exercise_count != 1 else ''}, "
            f"{kept} set{'s' if kept != 1 else ''}.",
            "success",
        )
        return redirect(url_for("today"))

    @app.route("/workouts/<int:workout_id>/discard", methods=["POST"])
    @login_required
    def workout_discard(workout_id: int):
        workout = _get_open_workout_or_404(workout_id)
        db.session.delete(workout)
        db.session.commit()
        flash("Workout discarded.", "info")
        return redirect(url_for("today"))

    @app.route("/exercises")
    @login_required
    def exercises_list():
        query = (request.args.get("q") or "").strip()[:EXERCISE_SEARCH_MAX_LENGTH]
        matches = _search_exercises(_visible_exercises_query().all(), query)
        context = {"groups": _group_by_pattern(matches), "query": query,
                   "match_count": len(matches)}
        # History restores also send HX-Request but replace the whole page.
        if (request.headers.get("HX-Request")
                and not request.headers.get("HX-History-Restore-Request")):
            return render_template("_exercise_list.html", **context)
        return render_template("exercises.html", **context)

    @app.route("/exercises/<slug>")
    @login_required
    def exercise_detail(slug: str):
        exercise = _visible_exercises_query().filter(Exercise.slug == slug).first()
        if exercise is None:
            abort(404)
        return render_template("exercise_detail.html", exercise=exercise)

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
