"""
Phase 1B2 regression: the full exercise library and its coverage.

Phase 5's generator fills each training-day slot with an exercise matching
the slot's movement pattern and the user's equipment. These tests guarantee
that lookup succeeds for every pattern × equipment profile, except for a
short, explicit list of gaps the generator must handle by falling back.
"""
from __future__ import annotations

import pytest

import exercise_vocab as vocab
from exercise_library import EXERCISES

# A vertical pull needs something overhead to pull from. Without a bar or a
# cable there is no honest option, so the generator falls back to a
# horizontal pull for these profiles (PLAN.md "Plan builder rules" §5).
KNOWN_GAPS = {
    ("vertical-pull", "dumbbells-only"),
    ("vertical-pull", "bodyweight"),
}


def _matches(pattern, profile):
    available = vocab.EQUIPMENT_PROFILES[profile]
    return [e["slug"] for e in EXERCISES
            if e["movement_pattern"] == pattern
            and vocab.fits_equipment(e["equipment"], available)]


COMBOS = [(p, prof) for p in vocab.MOVEMENT_PATTERNS for prof in vocab.EQUIPMENT_PROFILES]


class TestLibrarySize:
    def test_library_has_about_sixty_exercises(self):
        assert len(EXERCISES) >= 60


class TestCoverage:
    @pytest.mark.parametrize("pattern, profile",
                             [c for c in COMBOS if c not in KNOWN_GAPS])
    def test_every_pattern_has_an_option_for_every_profile(self, pattern, profile):
        assert _matches(pattern, profile), (
            f"No {pattern} exercise fits the {profile} profile")

    @pytest.mark.parametrize("pattern, profile", sorted(KNOWN_GAPS))
    def test_known_gaps_are_still_gaps(self, pattern, profile):
        """If someone adds an exercise that fills a gap, remove it from
        KNOWN_GAPS so the guarantee covers it from then on."""
        assert _matches(pattern, profile) == []

    @pytest.mark.parametrize("pattern", [
        "squat", "hinge", "single-leg", "horizontal-push",
        "vertical-push", "horizontal-pull", "vertical-pull",
    ])
    def test_full_gym_has_a_choice_of_compound_lifts(self, pattern):
        """Swapping an exercise (Phase 5C) needs at least two compound
        options for each main pattern when everything is available."""
        compounds = [e for e in EXERCISES
                     if e["movement_pattern"] == pattern and e["is_compound"]]
        assert len(compounds) >= 2, pattern


class TestVocabularyIsUsed:
    """A vocabulary value no exercise uses is either a typo-in-waiting or
    a filter that silently matches nothing."""

    def test_every_muscle_is_tagged_somewhere(self):
        used = set()
        for e in EXERCISES:
            used |= set(e["primary_muscles"]) | set(e["secondary_muscles"])
        assert set(vocab.MUSCLES) - used == set()

    def test_every_piece_of_equipment_is_used(self):
        used = set()
        for e in EXERCISES:
            used |= set(e["equipment"])
        assert set(vocab.EQUIPMENT) - used == set()

    def test_every_stress_is_used(self):
        used = set()
        for e in EXERCISES:
            used |= set(e["stresses"])
        assert set(vocab.STRESSES) - used == set()


class TestLimitationsLeaveOptions:
    @pytest.mark.parametrize("stress", vocab.STRESSES)
    @pytest.mark.parametrize("pattern", [
        "squat", "hinge", "horizontal-push", "horizontal-pull",
    ])
    def test_full_gym_has_an_option_avoiding_each_stress(self, pattern, stress):
        """A user reporting a limitation should still get every core slot
        filled in a full gym. Knees are exempt for squats: every squat
        loads the knees, so the generator substitutes a hinge instead."""
        if (pattern, stress) == ("squat", "knees"):
            pytest.skip("every squat loads the knees; generator substitutes")
        options = [e for e in EXERCISES
                   if e["movement_pattern"] == pattern and stress not in e["stresses"]]
        assert options, f"every {pattern} exercise stresses {stress}"


class TestLibraryLoadsIntoDatabase:
    def test_all_exercises_are_seeded(self, app):
        from models import Exercise
        with app.app_context():
            assert Exercise.query.filter_by(is_custom=False).count() == len(EXERCISES)

    def test_kettlebell_increment(self, app):
        """Kettlebells jump one bell size, not a plate pair."""
        from models import Exercise
        with app.app_context():
            swing = Exercise.query.filter_by(slug="kettlebell-swing").one()
            assert (swing.increment_lb, swing.increment_kg) == (8, 4)
