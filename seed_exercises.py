"""
Global exercise library seed.

`seed_exercises()` upserts every entry in EXERCISES by slug. It runs on
every app start (see create_app) and can be run by hand:

    python seed_exercises.py

Re-running is safe: unchanged rows are left alone, edited entries are
updated in place (keeping their id, so logged sets stay attached), and
exercises removed from this list are never deleted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from exercise_vocab import validate_exercise

# Field order: identity, classification, muscles, equipment, risk, progression.
EXERCISES: List[Dict] = [
    # --- squat ---
    {
        "slug": "barbell-back-squat", "name": "Barbell Back Squat",
        "movement_pattern": "squat", "is_compound": True, "difficulty": 2,
        "primary_muscles": ["quads", "glutes"],
        "secondary_muscles": ["adductors", "hamstrings", "lower-back"],
        "equipment": ["barbell", "rack"],
        "stresses": ["knees", "lower-back"],
        "increment_lb": 10, "increment_kg": 5,
    },
    {
        "slug": "goblet-squat", "name": "Goblet Squat",
        "movement_pattern": "squat", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["quads", "glutes"],
        "secondary_muscles": ["adductors", "abs"],
        "equipment": ["dumbbells"],
        "stresses": ["knees"],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    # --- hinge ---
    {
        "slug": "conventional-deadlift", "name": "Conventional Deadlift",
        "movement_pattern": "hinge", "is_compound": True, "difficulty": 2,
        "primary_muscles": ["hamstrings", "glutes", "lower-back"],
        "secondary_muscles": ["quads", "traps", "forearms"],
        "equipment": ["barbell"],
        "stresses": ["lower-back"],
        "increment_lb": 10, "increment_kg": 5,
    },
    {
        "slug": "romanian-deadlift", "name": "Romanian Deadlift",
        "movement_pattern": "hinge", "is_compound": True, "difficulty": 2,
        "primary_muscles": ["hamstrings", "glutes"],
        "secondary_muscles": ["lower-back", "forearms"],
        "equipment": ["barbell"],
        "stresses": ["lower-back"],
        "increment_lb": 10, "increment_kg": 5,
    },
    {
        "slug": "barbell-hip-thrust", "name": "Barbell Hip Thrust",
        "movement_pattern": "hinge", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["glutes"],
        "secondary_muscles": ["hamstrings"],
        "equipment": ["barbell", "bench"],
        "stresses": [],
        "increment_lb": 10, "increment_kg": 5,
    },
    # --- single-leg ---
    {
        "slug": "dumbbell-walking-lunge", "name": "Dumbbell Walking Lunge",
        "movement_pattern": "single-leg", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["quads", "glutes"],
        "secondary_muscles": ["adductors", "hamstrings"],
        "equipment": ["dumbbells"],
        "stresses": ["knees"],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    # --- horizontal push ---
    {
        "slug": "barbell-bench-press", "name": "Barbell Bench Press",
        "movement_pattern": "horizontal-push", "is_compound": True, "difficulty": 2,
        "primary_muscles": ["chest", "triceps"],
        "secondary_muscles": ["front-delts"],
        "equipment": ["barbell", "bench", "rack"],
        "stresses": ["shoulders"],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    {
        "slug": "dumbbell-bench-press", "name": "Dumbbell Bench Press",
        "movement_pattern": "horizontal-push", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["chest", "triceps"],
        "secondary_muscles": ["front-delts"],
        "equipment": ["dumbbells", "bench"],
        "stresses": ["shoulders"],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    {
        "slug": "push-up", "name": "Push-Up",
        "movement_pattern": "horizontal-push", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["chest", "triceps"],
        "secondary_muscles": ["front-delts", "abs"],
        "equipment": [],
        "stresses": ["wrists"],
        "increment_lb": None, "increment_kg": None,
    },
    # --- vertical push ---
    {
        "slug": "overhead-press", "name": "Overhead Press",
        "movement_pattern": "vertical-push", "is_compound": True, "difficulty": 2,
        "primary_muscles": ["front-delts", "triceps"],
        "secondary_muscles": ["side-delts", "upper-back", "abs"],
        "equipment": ["barbell", "rack"],
        "stresses": ["shoulders", "lower-back"],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    {
        "slug": "dumbbell-shoulder-press", "name": "Dumbbell Shoulder Press",
        "movement_pattern": "vertical-push", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["front-delts", "triceps"],
        "secondary_muscles": ["side-delts"],
        "equipment": ["dumbbells"],
        "stresses": ["shoulders"],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    # --- horizontal pull ---
    {
        "slug": "barbell-row", "name": "Barbell Row",
        "movement_pattern": "horizontal-pull", "is_compound": True, "difficulty": 2,
        "primary_muscles": ["upper-back", "lats"],
        "secondary_muscles": ["biceps", "rear-delts", "lower-back"],
        "equipment": ["barbell"],
        "stresses": ["lower-back"],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    {
        "slug": "one-arm-dumbbell-row", "name": "One-Arm Dumbbell Row",
        "movement_pattern": "horizontal-pull", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["lats", "upper-back"],
        "secondary_muscles": ["biceps", "rear-delts"],
        "equipment": ["dumbbells", "bench"],
        "stresses": [],
        "increment_lb": 5, "increment_kg": 2.5,
    },
    # --- vertical pull ---
    {
        "slug": "pull-up", "name": "Pull-Up",
        "movement_pattern": "vertical-pull", "is_compound": True, "difficulty": 3,
        "primary_muscles": ["lats", "upper-back"],
        "secondary_muscles": ["biceps", "rear-delts", "forearms"],
        "equipment": ["pull-up-bar"],
        "stresses": ["shoulders", "elbows"],
        "increment_lb": None, "increment_kg": None,
    },
    {
        "slug": "lat-pulldown", "name": "Lat Pulldown",
        "movement_pattern": "vertical-pull", "is_compound": True, "difficulty": 1,
        "primary_muscles": ["lats"],
        "secondary_muscles": ["upper-back", "biceps", "rear-delts"],
        "equipment": ["cable"],
        "stresses": [],
        "increment_lb": 10, "increment_kg": 5,
    },
]

SEEDED_FIELDS = (
    "name", "movement_pattern", "primary_muscles", "secondary_muscles",
    "equipment", "stresses", "difficulty", "is_compound",
    "increment_lb", "increment_kg",
)


class InvalidSeedData(ValueError):
    pass


@dataclass
class SeedResult:
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)


def validate_seed_data(entries: List[Dict]) -> None:
    errors: List[str] = []
    seen = set()
    for spec in entries:
        errors.extend(validate_exercise(spec))
        if spec.get("slug") in seen:
            errors.append(f"duplicate slug {spec.get('slug')!r}")
        seen.add(spec.get("slug"))
    if errors:
        raise InvalidSeedData("Invalid exercise seed data:\n  " + "\n  ".join(errors))


def seed_exercises(entries: List[Dict] = None) -> SeedResult:
    """Upsert global exercises by slug. Requires an app context."""
    from extensions import db
    from models import Exercise

    entries = EXERCISES if entries is None else entries
    validate_seed_data(entries)

    existing = {
        e.slug: e for e in Exercise.query.filter(Exercise.owner_user_id.is_(None))
    }
    result = SeedResult()
    for spec in entries:
        row = existing.get(spec["slug"])
        values = {f: _normalize(spec[f]) for f in SEEDED_FIELDS}
        if row is None:
            db.session.add(Exercise(slug=spec["slug"], is_custom=False, **values))
            result.created.append(spec["slug"])
            continue
        changed = False
        for f, v in values.items():
            if _normalize(getattr(row, f)) != v:
                setattr(row, f, v)
                changed = True
        (result.updated if changed else result.unchanged).append(spec["slug"])

    if result.created or result.updated:
        db.session.commit()
    return result


def _normalize(value):
    # Tuples and lists compare unequal, and JSON round-trips return lists.
    return list(value) if isinstance(value, tuple) else value


if __name__ == "__main__":
    # Importing app already seeds during create_app(), so this run usually
    # reports no changes; the total confirms the library is in place.
    from app import app
    from models import Exercise

    with app.app_context():
        r = seed_exercises()
        print(f"{Exercise.query.count()} exercises in library "
              f"(this run: created {len(r.created)}, updated {len(r.updated)})")
