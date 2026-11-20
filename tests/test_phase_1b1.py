"""
Phase 1B1 regression: exercise model, tag vocabularies, and the seed.

The plan generator (Phase 5) trusts these tags completely, so the seed data
is validated against the vocabularies, the seed must be safe to re-run on
a live database, and the vocabulary module must stay free of Flask so the
generator can import it without an app.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

import exercise_vocab as vocab
from seed_exercises import (
    EXERCISES, InvalidSeedData, seed_exercises, validate_seed_data,
)

ROOT = Path(__file__).resolve().parent.parent


def _valid_spec(**overrides):
    spec = {
        "slug": "test-press", "name": "Test Press",
        "movement_pattern": "horizontal-push", "is_compound": True,
        "difficulty": 1, "primary_muscles": ["chest"],
        "secondary_muscles": ["triceps"], "equipment": ["dumbbells"],
        "stresses": [], "increment_lb": 5, "increment_kg": 2.5,
    }
    spec.update(overrides)
    return spec


class TestSeedData:
    def test_seed_data_is_valid(self):
        """Every seeded tag must exist in its vocabulary, or the planner's
        filters silently miss exercises."""
        validate_seed_data(EXERCISES)

    def test_has_core_lift_set(self):
        assert len(EXERCISES) >= 15

    def test_slugs_are_unique(self):
        slugs = [e["slug"] for e in EXERCISES]
        assert len(slugs) == len(set(slugs))

    @pytest.mark.parametrize("pattern", [
        "squat", "hinge", "single-leg", "horizontal-push",
        "vertical-push", "horizontal-pull", "vertical-pull",
    ])
    def test_every_main_pattern_has_an_exercise(self, pattern):
        """The day templates in the plan builder are built from these slots."""
        assert any(e["movement_pattern"] == pattern for e in EXERCISES)

    def test_bodyweight_exercises_progress_by_reps(self):
        """No equipment means there's no plate to add."""
        for e in EXERCISES:
            if not e["equipment"]:
                assert e["increment_lb"] is None, e["slug"]


class TestValidation:
    def test_valid_spec_passes(self):
        assert vocab.validate_exercise(_valid_spec()) == []

    @pytest.mark.parametrize("overrides, fragment", [
        ({"slug": "Bad Slug"}, "slug"),
        ({"name": "  "}, "name is required"),
        ({"movement_pattern": "twist"}, "unknown movement_pattern"),
        ({"primary_muscles": ["pecs"]}, "unknown primary_muscles"),
        ({"primary_muscles": []}, "at least one primary muscle"),
        ({"secondary_muscles": ["chest"]}, "both primary and secondary"),
        ({"equipment": ["smith-machine"]}, "unknown equipment"),
        ({"equipment": "dumbbells"}, "equipment must be a list"),
        ({"stresses": ["neck"]}, "unknown stresses"),
        ({"stresses": ["knees", "knees"]}, "duplicate values"),
        ({"difficulty": 4}, "difficulty"),
        ({"difficulty": True}, "difficulty"),
        ({"is_compound": "yes"}, "is_compound"),
        ({"increment_kg": None}, "or neither"),
        ({"increment_lb": -5}, "positive number"),
    ])
    def test_invalid_specs_are_reported(self, overrides, fragment):
        errors = vocab.validate_exercise(_valid_spec(**overrides))
        assert any(fragment in e for e in errors), errors

    def test_bodyweight_spec_with_no_increments_is_valid(self):
        spec = _valid_spec(equipment=[], increment_lb=None, increment_kg=None)
        assert vocab.validate_exercise(spec) == []

    def test_seed_refuses_invalid_data(self, app):
        """A typo in the seed list must fail loudly at boot, not write a
        half-tagged row the planner can't use."""
        with app.app_context():
            with pytest.raises(InvalidSeedData, match="unknown equipment"):
                seed_exercises([_valid_spec(equipment=["smith-machine"])])

    def test_seed_refuses_duplicate_slugs(self):
        with pytest.raises(InvalidSeedData, match="duplicate slug"):
            validate_seed_data([_valid_spec(), _valid_spec()])


class TestVocabulary:
    def test_vocab_module_has_no_app_dependencies(self):
        """Phase 5's generator imports this module as a pure package."""
        tree = ast.parse((ROOT / "exercise_vocab.py").read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"flask", "flask_sqlalchemy", "sqlalchemy", "extensions", "models", "app"}
        assert not imported & forbidden

    def test_equipment_profiles_use_known_equipment(self):
        for name, items in vocab.EQUIPMENT_PROFILES.items():
            assert items <= set(vocab.EQUIPMENT), name

    def test_bodyweight_profile_is_empty(self):
        assert vocab.EQUIPMENT_PROFILES["bodyweight"] == frozenset()

    @pytest.mark.parametrize("required, available, expected", [
        ([], [], True),
        (["dumbbells"], ["dumbbells", "bench"], True),
        (["dumbbells", "bench"], ["dumbbells"], False),
        (["barbell"], vocab.EQUIPMENT_PROFILES["full-gym"], True),
    ])
    def test_fits_equipment(self, required, available, expected):
        assert vocab.fits_equipment(required, available) is expected


class TestSeeding:
    def test_app_startup_seeds_library(self, app):
        from models import Exercise
        with app.app_context():
            assert Exercise.query.count() == len(EXERCISES)
            squat = Exercise.query.filter_by(slug="barbell-back-squat").one()
            assert squat.equipment == ["barbell", "rack"]
            assert squat.is_custom is False
            assert squat.owner_user_id is None

    def test_reseed_is_a_no_op(self, app):
        """Runs on every boot, so an unchanged list must write nothing."""
        with app.app_context():
            result = seed_exercises()
        assert result.created == [] and result.updated == []
        assert len(result.unchanged) == len(EXERCISES)

    def test_reseed_updates_in_place_and_keeps_id(self, app):
        """Fixing a tag in the seed list must update the existing row, not
        create a new one, so logged sets stay attached to it."""
        from models import Exercise
        entries = copy.deepcopy(EXERCISES)
        squat = next(e for e in entries if e["slug"] == "barbell-back-squat")
        squat["name"] = "Back Squat"
        squat["stresses"] = ["knees"]
        with app.app_context():
            original_id = Exercise.query.filter_by(slug="barbell-back-squat").one().id
            result = seed_exercises(entries)
            row = Exercise.query.filter_by(slug="barbell-back-squat").one()
            assert result.updated == ["barbell-back-squat"]
            assert row.id == original_id
            assert row.name == "Back Squat"
            assert row.stresses == ["knees"]

    def test_seed_never_deletes(self, app):
        """Dropping an entry from the list must not delete a row that
        workouts may reference."""
        from models import Exercise
        with app.app_context():
            seed_exercises(EXERCISES[1:])
            assert Exercise.query.filter_by(slug=EXERCISES[0]["slug"]).count() == 1

    def test_seed_ignores_custom_exercises(self, app, client):
        """Custom exercises (Phase 1E) are owned by users; the seed must
        never overwrite them."""
        from conftest import sign_up
        from extensions import db
        from models import Exercise, User
        sign_up(client, "alice@example.com", "Alice")
        with app.app_context():
            alice = User.query.filter_by(email="alice@example.com").one()
            db.session.add(Exercise(
                slug="alice-sled-push", name="Sled Push",
                movement_pattern="conditioning", primary_muscles=["quads"],
                secondary_muscles=[], equipment=[], stresses=[],
                difficulty=2, is_compound=True, is_custom=True,
                owner_user_id=alice.id,
            ))
            db.session.commit()
            result = seed_exercises()
            assert "alice-sled-push" not in result.updated + result.unchanged
            assert Exercise.query.filter_by(slug="alice-sled-push").one().name == "Sled Push"


class TestExerciseModel:
    def test_increment_for_unit(self, app):
        from models import Exercise
        with app.app_context():
            bench = Exercise.query.filter_by(slug="barbell-bench-press").one()
            assert bench.increment_for("lb") == 5
            assert bench.increment_for("kg") == 2.5

    def test_is_bodyweight(self, app):
        from models import Exercise
        with app.app_context():
            assert Exercise.query.filter_by(slug="push-up").one().is_bodyweight
            assert not Exercise.query.filter_by(slug="goblet-squat").one().is_bodyweight
