"""
Phase 1C1 regression: workout lifecycle (start, resume, finish, discard).

The logging UI arrives in 1C2, so exercises and sets are created directly
in the database here. What's pinned is the server-side behavior that UI
will depend on: one open workout per user, the finish rules recorded in
PLAN.md, and strict per-user ownership.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from conftest import sign_up


def _body(resp) -> str:
    return " ".join(html.unescape(resp.get_data(as_text=True)).split())


def _user_id(app, email):
    from models import User
    with app.app_context():
        return User.query.filter_by(email=email).one().id


def _workouts(app, email):
    from models import Workout
    with app.app_context():
        return Workout.query.filter_by(user_id=_user_id(app, email)).all()


def _start(c):
    resp = c.post("/workouts/start")
    assert resp.status_code == 302
    return int(re.search(r"/workouts/(\d+)$", resp.headers["Location"]).group(1))


def _add(app, workout_id, slug, sets):
    """Attach an exercise and its sets: sets are (weight, reps, completed)."""
    from extensions import db
    from models import Exercise, Workout, WorkoutExercise, WorkoutSet
    with app.app_context():
        workout = db.session.get(Workout, workout_id)
        exercise = Exercise.query.filter_by(slug=slug).one()
        we = WorkoutExercise(exercise=exercise, position=len(workout.exercises))
        workout.exercises.append(we)
        for i, (weight, reps, completed) in enumerate(sets):
            we.sets.append(WorkoutSet(position=i, weight=weight, reps=reps,
                                      completed=completed, unit="lb"))
        db.session.commit()


@pytest.fixture
def alice(client):
    sign_up(client, "alice@example.com", "Alice")
    return client


class TestStart:
    def test_start_creates_open_workout_and_redirects(self, app, alice):
        workout_id = _start(alice)
        [workout] = _workouts(app, "alice@example.com")
        assert workout.id == workout_id
        assert workout.is_open
        assert alice.get(f"/workouts/{workout_id}").status_code == 200

    def test_second_start_resumes_instead_of_duplicating(self, app, alice):
        """Double-tapping Start must not create two open workouts."""
        first = _start(alice)
        assert _start(alice) == first
        assert len(_workouts(app, "alice@example.com")) == 1

    def test_database_rejects_second_open_workout(self, app, alice):
        """The partial unique index backstops the route check if two
        requests race past it."""
        from extensions import db
        from models import Workout
        _start(alice)
        with app.app_context():
            db.session.add(Workout(user_id=_user_id(app, "alice@example.com")))
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_finished_workouts_dont_block_a_new_one(self, app, alice):
        first = _start(alice)
        _add(app, first, "push-up", [(None, 10, True)])
        alice.post(f"/workouts/{first}/finish")
        second = _start(alice)
        assert second != first

    def test_start_requires_post(self, alice):
        assert alice.get("/workouts/start").status_code == 405

    def test_start_requires_login(self, client):
        resp = client.post("/workouts/start")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestToday:
    def test_idle_shows_start_button(self, alice):
        body = _body(alice.get("/today"))
        assert "Start empty workout" in body
        assert "Resume workout" not in body

    def test_open_workout_shows_resume_card(self, app, alice):
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat", [(135, 5, True), (135, 5, False)])
        body = _body(alice.get("/today"))
        assert "Resume workout" in body
        assert "Start empty workout" not in body
        assert "1 exercise · 2 sets" in body
        assert f'href="/workouts/{workout_id}"' in body

    def test_old_open_workout_is_still_resumable(self, app, alice):
        """Never auto-finished, however long it's been."""
        from extensions import db
        from models import Workout
        workout_id = _start(alice)
        with app.app_context():
            db.session.get(Workout, workout_id).started_at = datetime.utcnow() - timedelta(days=3)
            db.session.commit()
        body = _body(alice.get("/today"))
        assert "Started 3 days ago" in body
        assert "Resume workout" in body


class TestFinish:
    def test_keeps_logged_sets_checked_or_not(self, app, alice):
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat",
             [(135, 5, True), (135, 5, False)])
        resp = alice.post(f"/workouts/{workout_id}/finish", follow_redirects=True)
        assert "Workout saved: 1 exercise, 2 sets." in _body(resp)
        [workout] = _workouts(app, "alice@example.com")
        assert workout.finished_at is not None

    def test_drops_sets_missing_weight_or_reps(self, app, alice):
        from extensions import db
        from models import Workout
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat",
             [(135, 5, True), (None, 5, True), (135, None, True), (135, 0, False)])
        alice.post(f"/workouts/{workout_id}/finish")
        with app.app_context():
            sets = db.session.get(Workout, workout_id).exercises[0].sets
            assert [(s.weight, s.reps) for s in sets] == [(135, 5)]

    def test_rep_progressed_exercises_dont_need_a_weight(self, app, alice):
        """Push-ups and pull-ups are logged by reps; blank weight is normal."""
        from extensions import db
        from models import Workout
        workout_id = _start(alice)
        _add(app, workout_id, "pull-up", [(None, 8, True), (25, 5, True)])
        alice.post(f"/workouts/{workout_id}/finish")
        with app.app_context():
            sets = db.session.get(Workout, workout_id).exercises[0].sets
            assert [(s.weight, s.reps) for s in sets] == [(None, 8), (25, 5)]

    def test_drops_exercises_left_with_no_sets(self, app, alice):
        from extensions import db
        from models import Workout
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat", [(135, 5, True)])
        _add(app, workout_id, "barbell-bench-press", [])
        _add(app, workout_id, "barbell-row", [(None, None, False)])
        alice.post(f"/workouts/{workout_id}/finish")
        with app.app_context():
            slugs = [we.exercise.slug for we in db.session.get(Workout, workout_id).exercises]
            assert slugs == ["barbell-back-squat"]

    def test_nothing_logged_means_discard(self, app, alice):
        """Empty workouts never reach history."""
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat", [(None, None, False)])
        resp = alice.post(f"/workouts/{workout_id}/finish", follow_redirects=True)
        assert "Nothing was logged, so the workout was discarded." in _body(resp)
        assert _workouts(app, "alice@example.com") == []

    def test_finished_workout_is_no_longer_active(self, app, alice):
        workout_id = _start(alice)
        _add(app, workout_id, "push-up", [(None, 10, True)])
        alice.post(f"/workouts/{workout_id}/finish")
        assert alice.get(f"/workouts/{workout_id}").status_code == 404
        assert alice.post(f"/workouts/{workout_id}/finish").status_code == 404
        assert "Start empty workout" in _body(alice.get("/today"))

    def test_exercise_order_is_preserved(self, app, alice):
        from extensions import db
        from models import Workout
        workout_id = _start(alice)
        for slug in ("barbell-row", "barbell-back-squat", "overhead-press"):
            _add(app, workout_id, slug, [(95, 5, True)])
        alice.post(f"/workouts/{workout_id}/finish")
        with app.app_context():
            slugs = [we.exercise.slug for we in db.session.get(Workout, workout_id).exercises]
            assert slugs == ["barbell-row", "barbell-back-squat", "overhead-press"]


class TestDiscard:
    def test_discard_deletes_workout_and_sets(self, app, alice):
        from models import WorkoutExercise, WorkoutSet
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat", [(135, 5, True)])
        resp = alice.post(f"/workouts/{workout_id}/discard", follow_redirects=True)
        assert "Workout discarded." in _body(resp)
        assert _workouts(app, "alice@example.com") == []
        with app.app_context():
            assert WorkoutExercise.query.count() == 0
            assert WorkoutSet.query.count() == 0

    def test_discard_asks_for_confirmation(self, app, alice):
        workout_id = _start(alice)
        body = alice.get(f"/workouts/{workout_id}").get_data(as_text=True)
        assert "return confirm(" in body


class TestOwnership:
    @pytest.mark.parametrize("method, suffix", [
        ("get", ""), ("post", "/finish"), ("post", "/discard"),
    ])
    def test_other_users_workout_is_404(self, app, two_clients, method, suffix):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        sign_up(b, "bob@example.com", "Bob")
        workout_id = _start(a)
        resp = getattr(b, method)(f"/workouts/{workout_id}{suffix}")
        assert resp.status_code == 404
        assert len(_workouts(app, "alice@example.com")) == 1
        assert _workouts(app, "alice@example.com")[0].is_open

    def test_users_each_get_their_own_open_workout(self, app, two_clients):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        sign_up(b, "bob@example.com", "Bob")
        assert _start(a) != _start(b)


class TestModel:
    def test_client_ids_are_generated_and_unique(self, app, alice):
        from models import WorkoutSet
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat", [(135, 5, True), (135, 5, True)])
        with app.app_context():
            ids = [s.client_id for s in WorkoutSet.query.all()]
            assert len(ids) == 2 and len(set(ids)) == 2
            assert all(re.fullmatch(r"[0-9a-f-]{36}", i) for i in ids)

    def test_set_keeps_its_unit_when_preference_changes(self, app, alice):
        """Flipping lb/kg later must never rewrite logged weights."""
        from extensions import db
        from models import User, WorkoutSet
        workout_id = _start(alice)
        _add(app, workout_id, "barbell-back-squat", [(135, 5, True)])
        with app.app_context():
            User.query.filter_by(email="alice@example.com").one().unit_pref = "kg"
            db.session.commit()
            s = WorkoutSet.query.one()
            assert (s.weight, s.unit) == (135, "lb")

    @pytest.mark.parametrize("seconds, expected", [
        (5, "just now"), (300, "5 min ago"), (7200, "2 hr ago"),
        (86400 + 60, "yesterday"), (3 * 86400, "3 days ago"),
    ])
    def test_relative_time(self, seconds, expected):
        from app import _relative_time
        now = datetime(2026, 11, 25, 12, 0, 0)
        assert _relative_time(now - timedelta(seconds=seconds), now) == expected


class TestTabBar:
    def test_today_tab_is_active_during_a_workout(self, alice):
        workout_id = _start(alice)
        body = alice.get(f"/workouts/{workout_id}").get_data(as_text=True)
        current = re.search(r'aria-current="page"[^>]*>.*?</svg>\s*(\w+)', body, re.DOTALL)
        assert current.group(1) == "Today"
