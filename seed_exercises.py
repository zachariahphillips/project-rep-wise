"""
Global exercise library seed.

`seed_exercises()` upserts every entry in exercise_library.EXERCISES by
slug. It runs on every app start (see create_app) and can be run by hand:

    python seed_exercises.py

Re-running is safe: unchanged rows are left alone, edited entries are
updated in place (keeping their id, so logged sets stay attached), and
exercises removed from the library are never deleted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from exercise_library import EXERCISES
from exercise_vocab import validate_exercise

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
