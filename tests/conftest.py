"""
Shared pytest fixtures for the RepWise test suite.

Each test gets its own Flask app backed by a per-test SQLite file, so test
order is irrelevant. CSRF protection stays *on* in the test client so tests
exercise the same code path the browser does. The `Client` wrapper scrapes
the rotating CSRF token out of rendered HTML, the same way the htmx listener
in `base.html` reads it from the meta tag.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A fresh Flask app + empty SQLite file per test."""
    db_file = tmp_path / "test.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-not-for-production")
    monkeypatch.delenv("FLASK_ENV", raising=False)

    # Imported inside the fixture so env vars are read at create_app() time.
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app


class Client:
    """Thin wrapper around Flask's test_client that auto-refreshes the
    per-session CSRF token and emits htmx-style headers when asked."""

    # Any page that extends base.html renders the csrf-token meta tag.
    TOKEN_SOURCE_PATH = "/"

    def __init__(self, flask_client):
        self._c = flask_client
        self._token: Optional[str] = None

    def _scrape_token(self, html: str) -> None:
        m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
        if m:
            self._token = m.group(1)
            return
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        if m:
            self._token = m.group(1)

    def _ensure_token(self) -> None:
        if self._token is None:
            resp = self._c.get(self.TOKEN_SOURCE_PATH)
            self._scrape_token(resp.get_data(as_text=True))

    def _headers(self, htmx: bool) -> dict:
        if not htmx:
            return {}
        self._ensure_token()
        return {"HX-Request": "true", "X-CSRFToken": self._token or ""}

    def _body(self, data: Optional[dict]) -> dict:
        body = dict(data) if data else {}
        if "csrf_token" not in body:
            self._ensure_token()
            body["csrf_token"] = self._token or ""
        return body

    def get(self, path: str, *, htmx: bool = False, follow_redirects: bool = False):
        resp = self._c.get(path, headers=self._headers(htmx),
                           follow_redirects=follow_redirects)
        self._scrape_token(resp.get_data(as_text=True))
        return resp

    def post(self, path: str, *, data: Optional[dict] = None, htmx: bool = False,
             follow_redirects: bool = False):
        resp = self._c.post(path, data=self._body(data), headers=self._headers(htmx),
                            follow_redirects=follow_redirects)
        self._scrape_token(resp.get_data(as_text=True))
        return resp

    def put(self, path: str, *, data: Optional[dict] = None, htmx: bool = True):
        resp = self._c.put(path, data=self._body(data), headers=self._headers(htmx))
        self._scrape_token(resp.get_data(as_text=True))
        return resp

    def delete(self, path: str, *, htmx: bool = True):
        resp = self._c.delete(path, headers=self._headers(htmx))
        self._scrape_token(resp.get_data(as_text=True))
        return resp


@pytest.fixture
def client(app):
    """A Client wired up to a fresh test cookie jar."""
    return Client(app.test_client())


@pytest.fixture
def two_clients(app):
    """Two independent cookie jars on the same app, for cross-user isolation."""
    return Client(app.test_client()), Client(app.test_client())


# ---- helpers callers re-use ----

DEFAULT_PASSWORD = "testpass123"


def sign_up(c: Client, email: str, name: str, password: str = DEFAULT_PASSWORD,
            unit_pref: str = "lb"):
    """Create an account; expects landing on /today signed in."""
    resp = c.post("/signup", data={
        "name": name, "email": email, "password": password,
        "unit_pref": unit_pref, "submit": "Create account",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert resp.request.path == "/today", "signup didn't land on /today"
    return resp


def log_in(c: Client, email: str, password: str = DEFAULT_PASSWORD, *,
           remember: bool = True, next_url: Optional[str] = None,
           follow_redirects: bool = True):
    data = {"email": email, "password": password, "submit": "Sign in"}
    if remember:
        data["remember"] = "y"
    path = "/login" if next_url is None else f"/login?next={next_url}"
    return c.post(path, data=data, follow_redirects=follow_redirects)


def log_out(c: Client):
    return c.post("/logout", follow_redirects=True)
