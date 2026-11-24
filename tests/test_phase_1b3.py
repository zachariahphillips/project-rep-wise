"""
Phase 1B3 regression: exercise browse, search, detail, and the tab bar.

The search partial is the exercise picker Phase 1C reuses, so its matching
rules and htmx behavior are pinned here. Visibility rules (global plus your
own custom exercises, never someone else's) are pinned now so Phase 1E
inherits them.
"""
from __future__ import annotations

import html
import re

import pytest

from conftest import sign_up
from exercise_library import EXERCISES


ROW_ID_RE = r'id="exercise-row-([a-z0-9-]+)"'


def _body(resp) -> str:
    """Decoded text with whitespace collapsed, since templates wrap lines."""
    return " ".join(html.unescape(resp.get_data(as_text=True)).split())


def _listed_slugs(resp):
    return re.findall(ROW_ID_RE, resp.get_data(as_text=True))


def _add_custom(app, email, slug, name):
    from extensions import db
    from models import Exercise, User
    with app.app_context():
        owner = User.query.filter_by(email=email).one()
        db.session.add(Exercise(
            slug=slug, name=name, movement_pattern="conditioning",
            primary_muscles=["quads"], secondary_muscles=[], equipment=[],
            stresses=[], difficulty=1, is_compound=True, is_custom=True,
            owner_user_id=owner.id,
        ))
        db.session.commit()


@pytest.fixture
def alice(client):
    sign_up(client, "alice@example.com", "Alice")
    return client


class TestBrowse:
    def test_requires_login(self, client):
        resp = client.get("/exercises")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_lists_whole_library(self, alice):
        assert len(_listed_slugs(alice.get("/exercises"))) == len(EXERCISES)

    def test_groups_follow_vocabulary_order(self, alice):
        """Main lifts first, accessories after, in the same order the plan
        builder thinks about them."""
        body = alice.get("/exercises").get_data(as_text=True)
        headings = re.findall(r'id="pattern-([a-z-]+)"', body)
        assert headings[:3] == ["squat", "hinge", "single-leg"]
        assert headings[-1] == "conditioning"

    def test_exercises_are_alphabetical_within_a_group(self, alice):
        body = alice.get("/exercises").get_data(as_text=True)
        squat_section = body.split('id="pattern-squat"')[1].split("</section>")[0]
        slugs = re.findall(ROW_ID_RE, squat_section)
        names = {e["slug"]: e["name"] for e in EXERCISES}
        assert [names[s] for s in slugs] == sorted(names[s] for s in slugs)

    def test_rows_show_equipment_and_muscles(self, alice):
        body = _body(alice.get("/exercises"))
        assert "Bodyweight · Chest, Triceps" in body  # push-up
        assert "Barbell, Rack · Quads, Glutes" in body  # back squat


class TestSearch:
    def test_search_by_name(self, alice):
        slugs = _listed_slugs(alice.get("/exercises?q=deadlift"))
        assert "conventional-deadlift" in slugs
        assert "romanian-deadlift" in slugs
        assert "barbell-back-squat" not in slugs

    def test_search_is_case_insensitive_and_trims(self, alice):
        assert _listed_slugs(alice.get("/exercises?q=%20%20DEADLIFT%20")) == \
            _listed_slugs(alice.get("/exercises?q=deadlift"))

    def test_search_by_muscle(self, alice):
        slugs = _listed_slugs(alice.get("/exercises?q=hamstrings"))
        assert "lying-leg-curl" in slugs
        assert "plank" not in slugs

    def test_multiple_words_narrow_results(self, alice):
        """'dumbbell chest' should mean dumbbell AND chest."""
        slugs = _listed_slugs(alice.get("/exercises?q=dumbbell+chest"))
        assert "dumbbell-bench-press" in slugs
        assert "barbell-bench-press" not in slugs
        assert "dumbbell-curl" not in slugs

    def test_hyphenated_tags_match_spaced_words(self, alice):
        """People type 'lower back', not 'lower-back'."""
        slugs = _listed_slugs(alice.get("/exercises?q=lower+back"))
        assert "conventional-deadlift" in slugs

    def test_bodyweight_keyword(self, alice):
        slugs = _listed_slugs(alice.get("/exercises?q=bodyweight"))
        assert "push-up" in slugs
        assert "barbell-bench-press" not in slugs

    def test_no_matches_shows_empty_state(self, alice):
        resp = alice.get("/exercises?q=zzzz")
        assert _listed_slugs(resp) == []
        assert 'No exercises match "zzzz"' in _body(resp)

    def test_overlong_query_is_truncated_not_rejected(self, alice):
        resp = alice.get("/exercises?q=" + "a" * 500)
        assert resp.status_code == 200

    def test_htmx_search_returns_only_the_list(self, alice):
        """The live search swaps #exercise-list; a full page would nest a
        second header and tab bar inside it."""
        resp = alice.get("/exercises?q=squat", htmx=True)
        body = resp.get_data(as_text=True)
        assert '<div id="exercise-list">' in body
        assert "<html" not in body
        assert "barbell-back-squat" in body

    def test_htmx_history_restore_gets_full_page(self, app, alice):
        resp = alice._c.get("/exercises?q=squat", headers={
            "HX-Request": "true", "HX-History-Restore-Request": "true"})
        assert "<html" in resp.get_data(as_text=True)

    def test_search_box_works_without_javascript(self, alice):
        body = alice.get("/exercises?q=row").get_data(as_text=True)
        assert re.search(r'<form method="get" action="/exercises"', body)
        assert 'value="row"' in body


class TestVisibility:
    def test_own_custom_exercise_is_listed(self, app, alice):
        _add_custom(app, "alice@example.com", "alice-sled-push", "Sled Push")
        assert "alice-sled-push" in _listed_slugs(alice.get("/exercises"))

    def test_other_users_custom_exercise_is_hidden(self, app, two_clients):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        sign_up(b, "bob@example.com", "Bob")
        _add_custom(app, "alice@example.com", "alice-sled-push", "Sled Push")
        assert "alice-sled-push" not in _listed_slugs(b.get("/exercises"))
        assert "alice-sled-push" not in _listed_slugs(b.get("/exercises?q=sled"))
        assert b.get("/exercises/alice-sled-push").status_code == 404


class TestDetail:
    def test_detail_shows_tags(self, alice):
        resp = alice.get("/exercises/barbell-back-squat")
        body = _body(resp)
        assert resp.status_code == 200
        assert "Barbell Back Squat" in body
        assert "Squat · Compound · Intermediate" in body
        for text in ("Quads", "Glutes", "Lower back", "Rack", "Knees"):
            assert text in body

    def test_increment_uses_lb_preference(self, alice):
        assert "Add 10 lb once you hit all your reps." in _body(
            alice.get("/exercises/barbell-back-squat"))

    def test_increment_uses_kg_preference(self, client):
        sign_up(client, "kg@example.com", "Kilo", unit_pref="kg")
        body = _body(client.get("/exercises/barbell-bench-press"))
        assert "Add 2.5 kg once you hit all your reps." in body

    def test_bodyweight_exercise_progresses_by_reps(self, alice):
        body = _body(alice.get("/exercises/pull-up"))
        assert "Add reps before anything else" in body
        assert "Add 0" not in body

    def test_bodyweight_equipment_copy(self, alice):
        assert "bodyweight only" in _body(alice.get("/exercises/push-up"))

    def test_no_stress_section_when_none(self, alice):
        assert "Go easy if" not in _body(alice.get("/exercises/barbell-hip-thrust"))

    def test_unknown_slug_is_404(self, alice):
        assert alice.get("/exercises/not-a-real-lift").status_code == 404

    def test_tag_labels(self):
        from exercise_vocab import label
        assert label("horizontal-push") == "Horizontal push"
        assert label("pull-up-bar") == "Pull-up bar"
        assert label("single-leg") == "Single-leg"


class TestTabBar:
    def test_hidden_when_signed_out(self, client):
        assert 'aria-label="Main"' not in client.get("/").get_data(as_text=True)

    @pytest.mark.parametrize("path, active", [
        ("/today", "Today"),
        ("/exercises", "Exercises"),
        ("/exercises/push-up", "Exercises"),
    ])
    def test_active_tab_is_marked(self, alice, path, active):
        body = alice.get(path).get_data(as_text=True)
        current = re.search(r'aria-current="page"[^>]*>.*?</svg>\s*(\w+)', body, re.DOTALL)
        assert current is not None
        assert current.group(1) == active
        assert body.count('aria-current="page"') == 1
