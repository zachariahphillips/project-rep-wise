"""
Phase 1A regression: email/password auth.

Guards signup (normalization, duplicates, validation, unit preference),
login (wrong password, remember-me, safe `?next=`), logout (POST only), and
the signed-in gate on /today. Security-sensitive behavior ported from
PantryPal (pbkdf2 hashing, the backslash open-redirect fix) is pinned here
so it can't quietly regress.
"""
from __future__ import annotations

import html
import re

import pytest

from conftest import DEFAULT_PASSWORD, log_in, log_out, sign_up


def _body(resp) -> str:
    # Jinja autoescapes apostrophes to &#39;; decode for assertions only.
    return html.unescape(resp.get_data(as_text=True))


def _user(app, email):
    from models import User
    with app.app_context():
        return User.query.filter_by(email=email).first()


class TestSignup:
    def test_signup_creates_user_and_lands_on_today(self, app, client):
        resp = sign_up(client, "alice@example.com", "Alice Smith")
        body = _body(resp)
        assert "Hey Alice" in body
        assert "Welcome to RepWise, Alice!" in body
        assert _user(app, "alice@example.com") is not None

    def test_email_is_normalized(self, app, client):
        """Users type emails with stray caps/spaces on phones; login must
        still find them."""
        sign_up(client, "  Alice@Example.COM ", "Alice")
        assert _user(app, "alice@example.com") is not None

    def test_duplicate_email_is_rejected(self, app, two_clients):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        resp = b.post("/signup", data={
            "name": "Imposter", "email": "ALICE@example.com",
            "password": DEFAULT_PASSWORD, "unit_pref": "lb",
        })
        assert resp.status_code == 200
        assert "already exists" in _body(resp)
        from models import User
        with app.app_context():
            assert User.query.count() == 1

    @pytest.mark.parametrize("field, value, message", [
        ("name", "", "Please enter your name."),
        ("email", "not-an-email", "valid email"),
        ("password", "short", "at least 8 characters"),
        ("unit_pref", "stone", "Not a valid choice"),
    ])
    def test_validation_errors_render_inline(self, app, client, field, value, message):
        data = {"name": "Alice", "email": "alice@example.com",
                "password": DEFAULT_PASSWORD, "unit_pref": "lb"}
        data[field] = value
        resp = client.post("/signup", data=data)
        assert resp.status_code == 200
        assert message in _body(resp)
        assert _user(app, "alice@example.com") is None

    @pytest.mark.parametrize("unit", ["lb", "kg"])
    def test_unit_preference_is_stored(self, app, client, unit):
        """Phase 1C pre-fills weights in this unit."""
        sign_up(client, "alice@example.com", "Alice", unit_pref=unit)
        assert _user(app, "alice@example.com").unit_pref == unit

    def test_password_is_hashed_with_pbkdf2(self, app, client):
        """scrypt (Werkzeug's default) crashes on macOS system Python."""
        sign_up(client, "alice@example.com", "Alice")
        user = _user(app, "alice@example.com")
        assert user.password_hash.startswith("pbkdf2:sha256")
        assert DEFAULT_PASSWORD not in user.password_hash

    def test_signed_in_user_visiting_signup_is_redirected(self, client):
        sign_up(client, "alice@example.com", "Alice")
        resp = client.get("/signup")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/today")


class TestLogin:
    def test_login_success(self, two_clients):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        resp = log_in(b, "alice@example.com")
        assert resp.request.path == "/today"
        assert "Hey Alice" in _body(resp)

    def test_login_is_case_insensitive_on_email(self, two_clients):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        resp = log_in(b, "ALICE@Example.com")
        assert resp.request.path == "/today"

    @pytest.mark.parametrize("email, password", [
        ("alice@example.com", "wrong-password"),
        ("nobody@example.com", DEFAULT_PASSWORD),
    ])
    def test_bad_credentials_share_one_message(self, two_clients, email, password):
        """Same copy for wrong password and unknown email, so the form
        doesn't reveal which emails have accounts."""
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        resp = log_in(b, email, password)
        assert resp.request.path == "/login"
        assert "Invalid email or password." in _body(resp)

    def test_remember_me_sets_persistent_cookie(self, app, two_clients):
        """Phone users should stay signed in across browser restarts."""
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        log_in(b, "alice@example.com", remember=True)
        assert b._c.get_cookie("remember_token") is not None

    def test_unchecked_remember_skips_persistent_cookie(self, app, two_clients):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        log_in(b, "alice@example.com", remember=False)
        assert b._c.get_cookie("remember_token") is None

    def test_remember_checkbox_defaults_on(self, client):
        body = client.get("/login").get_data(as_text=True)
        checkbox = re.search(r'<input[^>]*name="remember"[^>]*>', body)
        assert checkbox is not None
        assert "checked" in checkbox.group(0)


class TestNextRedirect:
    def test_anonymous_today_redirects_to_login_with_next(self, client):
        resp = client.get("/today")
        assert resp.status_code == 302
        assert "/login?next=%2Ftoday" in resp.headers["Location"]

    def test_safe_next_is_honored(self, two_clients):
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        resp = log_in(b, "alice@example.com", next_url="/today",
                      follow_redirects=False)
        assert resp.headers["Location"] == "/today"

    @pytest.mark.parametrize("evil", [
        "//evil.com",
        "/\\evil.com",
        "http://evil.com",
        "javascript:alert(1)",
    ])
    def test_unsafe_next_falls_back_to_today(self, two_clients, evil):
        """Open-redirect guard. `/\\evil.com` is the case a naive
        startswith('/') check misses: browsers normalize it to //evil.com."""
        a, b = two_clients
        sign_up(a, "alice@example.com", "Alice")
        resp = log_in(b, "alice@example.com", next_url=evil,
                      follow_redirects=False)
        assert resp.headers["Location"] == "/today"


class TestLogout:
    def test_logout_signs_out(self, client):
        sign_up(client, "alice@example.com", "Alice")
        resp = log_out(client)
        assert resp.request.path == "/login"
        assert "signed out" in _body(resp)
        assert client.get("/today").status_code == 302

    def test_logout_rejects_get(self, client):
        """GET logout would let any <img src="/logout"> sign users out."""
        sign_up(client, "alice@example.com", "Alice")
        assert client.get("/logout").status_code == 405

    def test_header_shows_sign_out_only_when_signed_in(self, client):
        assert "Sign out" not in client.get("/").get_data(as_text=True)
        sign_up(client, "alice@example.com", "Alice")
        assert "Sign out" in client.get("/today").get_data(as_text=True)


class TestLanding:
    def test_anonymous_landing_links_to_auth(self, client):
        body = client.get("/").get_data(as_text=True)
        assert 'href="/signup"' in body
        assert 'href="/login"' in body

    def test_signed_in_landing_redirects_to_today(self, client):
        sign_up(client, "alice@example.com", "Alice")
        resp = client.get("/")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/today")
