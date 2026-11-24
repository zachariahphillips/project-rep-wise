"""
Controlled vocabularies for tagging exercises, plus validation.

Pure Python with no Flask or DB imports: the seed script, the future
custom-exercise form (1E), and the plan generator (5B) all share these
lists, and the generator must stay importable without an app.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Mapping

MOVEMENT_PATTERNS = (
    "squat",
    "hinge",
    "single-leg",
    "horizontal-push",
    "vertical-push",
    "horizontal-pull",
    "vertical-pull",
    "arms",
    "core",
    "calves",
    "conditioning",
)

MUSCLES = (
    "quads",
    "hamstrings",
    "glutes",
    "adductors",
    "calves",
    "chest",
    "front-delts",
    "side-delts",
    "rear-delts",
    "lats",
    "upper-back",
    "traps",
    "lower-back",
    "biceps",
    "triceps",
    "forearms",
    "abs",
    "obliques",
)

# An empty equipment list means bodyweight only.
EQUIPMENT = (
    "barbell",
    "rack",
    "bench",
    "dumbbells",
    "kettlebell",
    "cable",
    "machine",
    "pull-up-bar",
    "dip-station",
)

# What each questionnaire answer in Phase 5A means in equipment terms.
EQUIPMENT_PROFILES = {
    "full-gym": frozenset(EQUIPMENT),
    "home-gym": frozenset({"barbell", "rack", "bench", "dumbbells", "pull-up-bar"}),
    "dumbbells-only": frozenset({"dumbbells"}),
    "bodyweight": frozenset(),
}

# Joints or regions an exercise loads heavily; the planner filters on these
# when a user reports a limitation.
STRESSES = (
    "knees",
    "lower-back",
    "shoulders",
    "elbows",
    "wrists",
    "hips",
)

DIFFICULTY_MIN = 1
DIFFICULTY_MAX = 3
DIFFICULTY_LABELS = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}

# Tags whose hyphen is part of the word, not a space.
_LABEL_OVERRIDES = {
    "pull-up-bar": "Pull-up bar",
    "single-leg": "Single-leg",
}


def label(tag: str) -> str:
    """Display text for a tag: 'horizontal-push' -> 'Horizontal push'."""
    if tag in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[tag]
    text = tag.replace("-", " ")
    return text[:1].upper() + text[1:]

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_LIST_FIELDS = {
    "primary_muscles": MUSCLES,
    "secondary_muscles": MUSCLES,
    "equipment": EQUIPMENT,
    "stresses": STRESSES,
}


def fits_equipment(required: Iterable[str], available: Iterable[str]) -> bool:
    """True if every piece of required equipment is available."""
    return set(required) <= set(available)


def validate_exercise(spec: Mapping) -> List[str]:
    """Return human-readable problems with an exercise spec; empty means valid."""
    errors: List[str] = []

    slug = spec.get("slug") or ""
    if not SLUG_RE.match(slug):
        errors.append(f"slug {slug!r} must be lowercase words joined by hyphens")

    if not (spec.get("name") or "").strip():
        errors.append(f"{slug}: name is required")

    if spec.get("movement_pattern") not in MOVEMENT_PATTERNS:
        errors.append(f"{slug}: unknown movement_pattern {spec.get('movement_pattern')!r}")

    for field, vocab in _LIST_FIELDS.items():
        values = spec.get(field)
        if not isinstance(values, (list, tuple)):
            errors.append(f"{slug}: {field} must be a list")
            continue
        unknown = [v for v in values if v not in vocab]
        if unknown:
            errors.append(f"{slug}: unknown {field} {unknown}")
        if len(set(values)) != len(values):
            errors.append(f"{slug}: duplicate values in {field}")

    if not spec.get("primary_muscles"):
        errors.append(f"{slug}: needs at least one primary muscle")
    overlap = set(spec.get("primary_muscles") or []) & set(spec.get("secondary_muscles") or [])
    if overlap:
        errors.append(f"{slug}: {sorted(overlap)} listed as both primary and secondary")

    difficulty = spec.get("difficulty")
    # bool is a subclass of int, so True would otherwise pass as 1.
    if (not isinstance(difficulty, int) or isinstance(difficulty, bool)
            or not DIFFICULTY_MIN <= difficulty <= DIFFICULTY_MAX):
        errors.append(f"{slug}: difficulty must be an integer {DIFFICULTY_MIN}-{DIFFICULTY_MAX}")

    if not isinstance(spec.get("is_compound"), bool):
        errors.append(f"{slug}: is_compound must be true or false")

    # Both increments set means "progress by adding weight"; both None means
    # "progress by reps" (bodyweight moves). Mixed would leave one unit
    # without a progression rule.
    inc_lb, inc_kg = spec.get("increment_lb"), spec.get("increment_kg")
    if (inc_lb is None) != (inc_kg is None):
        errors.append(f"{slug}: set both increment_lb and increment_kg, or neither")
    for label, inc in (("increment_lb", inc_lb), ("increment_kg", inc_kg)):
        if inc is not None and (not isinstance(inc, (int, float)) or inc <= 0):
            errors.append(f"{slug}: {label} must be a positive number")

    return errors
