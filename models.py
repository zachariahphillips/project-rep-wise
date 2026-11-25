"""
SQLAlchemy models. See PLAN.md "Data model" for where this is headed.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

UNIT_CHOICES = ("lb", "kg")
DEFAULT_UNIT = "lb"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    # Display/entry preference only. Logged sets store their own unit, so
    # flipping this never rewrites history.
    unit_pref = db.Column(db.String(2), nullable=False, default=DEFAULT_UNIT)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        # Werkzeug 3 defaults to scrypt, which macOS system Python (LibreSSL)
        # lacks, so pbkdf2 is pinned explicitly.
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name.strip() else self.name

    def __repr__(self) -> str:
        return f"<User {self.email!r} (id={self.id})>"


class Exercise(db.Model):
    """A movement in the library. Tag values come from exercise_vocab.

    Global exercises (owner_user_id NULL) are managed by seed_exercises.py;
    custom ones (Phase 1E) belong to a single user. Slugs are unique across
    both, so 1E must generate collision-free slugs for custom exercises.
    """
    __tablename__ = "exercises"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    movement_pattern = db.Column(db.String(32), nullable=False, index=True)
    primary_muscles = db.Column(db.JSON, nullable=False, default=list)
    secondary_muscles = db.Column(db.JSON, nullable=False, default=list)
    equipment = db.Column(db.JSON, nullable=False, default=list)
    stresses = db.Column(db.JSON, nullable=False, default=list)
    difficulty = db.Column(db.Integer, nullable=False)
    is_compound = db.Column(db.Boolean, nullable=False)
    # NULL increments mean the exercise progresses by reps, not load.
    increment_lb = db.Column(db.Float, nullable=True)
    increment_kg = db.Column(db.Float, nullable=True)
    is_custom = db.Column(db.Boolean, nullable=False, default=False)
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def is_bodyweight(self) -> bool:
        return not self.equipment

    @property
    def weight_is_optional(self) -> bool:
        """Rep-progressed moves (push-ups, pull-ups, planks) can be logged
        without a weight; any weight entered is added load."""
        return self.increment_lb is None

    def increment_for(self, unit: str):
        return self.increment_kg if unit == "kg" else self.increment_lb

    def __repr__(self) -> str:
        return f"<Exercise {self.slug!r} (id={self.id})>"


class Workout(db.Model):
    """One training session. finished_at NULL means in progress."""
    __tablename__ = "workouts"
    __table_args__ = (
        # Backstops the "resume instead of start a second" rule against a
        # double-tapped Start button.
        db.Index(
            "uq_one_open_workout_per_user", "user_id", unique=True,
            sqlite_where=text("finished_at IS NULL"),
            postgresql_where=text("finished_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    user = db.relationship("User", backref=db.backref("workouts", lazy="dynamic"))
    exercises = db.relationship(
        "WorkoutExercise", backref="workout",
        order_by="WorkoutExercise.position",
        cascade="all, delete-orphan",
    )

    @property
    def is_open(self) -> bool:
        return self.finished_at is None

    @property
    def set_count(self) -> int:
        return sum(len(we.sets) for we in self.exercises)

    def prune_unlogged(self) -> int:
        """Drop sets that weren't actually logged, then exercises left with
        no sets. Returns the number of sets kept."""
        for we in list(self.exercises):
            for s in list(we.sets):
                if not s.is_logged:
                    we.sets.remove(s)
            if not we.sets:
                self.exercises.remove(we)
        return self.set_count

    def __repr__(self) -> str:
        return f"<Workout id={self.id} user={self.user_id} open={self.is_open}>"


class WorkoutExercise(db.Model):
    """An exercise within a workout, so it keeps its place before any sets
    are logged."""
    __tablename__ = "workout_exercises"

    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(
        db.Integer, db.ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercises.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False)

    exercise = db.relationship("Exercise")
    sets = db.relationship(
        "WorkoutSet", backref="workout_exercise",
        order_by="WorkoutSet.position",
        cascade="all, delete-orphan",
    )


class WorkoutSet(db.Model):
    __tablename__ = "workout_sets"

    id = db.Column(db.Integer, primary_key=True)
    # Generated by the client in Phase 9 so a retried offline sync can't
    # insert the same set twice.
    client_id = db.Column(
        db.String(36), unique=True, nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    workout_exercise_id = db.Column(
        db.Integer, db.ForeignKey("workout_exercises.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    position = db.Column(db.Integer, nullable=False)
    weight = db.Column(db.Float, nullable=True)
    # Stored per set so changing the user's unit preference never rewrites history.
    unit = db.Column(db.String(2), nullable=False, default=DEFAULT_UNIT)
    reps = db.Column(db.Integer, nullable=True)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    is_warmup = db.Column(db.Boolean, nullable=False, default=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def is_logged(self) -> bool:
        """Kept on finish: has reps, and a weight unless the exercise is
        rep-progressed. Checked-off state doesn't matter."""
        if not self.reps or self.reps <= 0:
            return False
        if self.weight is None:
            return self.workout_exercise.exercise.weight_is_optional
        return self.weight >= 0
