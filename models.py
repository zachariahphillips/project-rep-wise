"""
SQLAlchemy models. See PLAN.md "Data model" for where this is headed.
"""
from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
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

    def increment_for(self, unit: str):
        return self.increment_kg if unit == "kg" else self.increment_lb

    def __repr__(self) -> str:
        return f"<Exercise {self.slug!r} (id={self.id})>"
