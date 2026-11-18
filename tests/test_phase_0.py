"""
Phase 0 regression: the skeleton boots, is safe to deploy, and stays
token-free.

These guard the load-bearing setup that every later phase depends on:
the landing page renders with a CSRF token, /healthz reports the phase and
fails loudly when the DB is gone, production refuses a placeholder secret,
and ProxyFix makes HTTPS visible behind the host's proxy.
"""
from __future__ import annotations

import importlib

import pytest
from flask import request, url_for


class TestLandingPage:
    def test_index_renders(self, client):
        """The landing page is the Phase 0 "it runs" proof."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "RepWise" in resp.get_data(as_text=True)

    def test_base_template_exposes_csrf_meta(self, client):
        """htmx reads the token from this meta tag on every request, and the
        test Client scrapes it the same way. Losing it breaks every POST."""
        body = client.get("/").get_data(as_text=True)
        assert '<meta name="csrf-token" content="' in body

    def test_csrf_is_enforced(self, app):
        """A POST without a token must be rejected, so later phases can't
        accidentally ship an unprotected form."""
        app.add_url_rule("/_csrf_probe", "csrf_probe",
                         lambda: "ok", methods=["POST"])
        resp = app.test_client().post("/_csrf_probe")
        assert resp.status_code == 400


class TestHealthz:
    def test_reports_ok_and_phase(self, client):
        """Deploy smoke checks and uptime pings read this shape."""
        resp = client.get("/healthz")
        assert resp.status_code == 200
        from app import APP_PHASE
        assert resp.get_json() == {"status": "ok", "phase": APP_PHASE}

    def test_returns_503_when_database_unavailable(self, app, monkeypatch):
        """A green health check over a dead DB would hide real outages."""
        from extensions import db

        def boom(*_args, **_kwargs):
            raise RuntimeError("db is down")

        monkeypatch.setattr(db.session, "execute", boom)
        resp = app.test_client().get("/healthz")
        assert resp.status_code == 503
        assert resp.get_json()["database"] == "unavailable"


class TestSecretKeyGuard:
    """Production must never boot with a forgeable session key. The module
    body runs `app = create_app()`, so the reload itself is the call under
    test and has to sit inside pytest.raises."""

    def _reload_app_module(self):
        import app as app_module
        return importlib.reload(app_module)

    def test_production_with_placeholder_secret_refuses_to_start(
            self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p.sqlite3'}")
        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.setenv("FLASK_SECRET_KEY", "dev-secret-change-me-in-env")
        with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
            self._reload_app_module()

    def test_production_with_empty_secret_refuses_to_start(
            self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p.sqlite3'}")
        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.setenv("FLASK_SECRET_KEY", "")
        with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
            self._reload_app_module()

    def test_production_with_real_secret_boots_with_secure_cookies(
            self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p.sqlite3'}")
        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 64)
        module = self._reload_app_module()
        assert module.app.config["SESSION_COOKIE_SECURE"] is True
        assert module.app.config["SESSION_COOKIE_HTTPONLY"] is True

    def test_dev_with_placeholder_secret_boots(self, monkeypatch, tmp_path):
        """`python app.py` must keep working locally with no .env."""
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p.sqlite3'}")
        monkeypatch.delenv("FLASK_ENV", raising=False)
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        module = self._reload_app_module()
        assert module.app.config["SECRET_KEY"] == "dev-secret-change-me-in-env"


class TestProxyFix:
    def test_forwarded_https_is_trusted(self, app):
        """Behind the host's HTTPS proxy, external URLs must be https://.
        Goes through test_client (not test_request_context) because only a
        real request traverses app.wsgi_app, where ProxyFix lives."""
        captured = {}

        def probe():
            captured["is_secure"] = request.is_secure
            captured["url"] = url_for("index", _external=True)
            return "ok"

        app.add_url_rule("/_proxy_probe", "proxy_probe", probe)
        app.test_client().get("/_proxy_probe", headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "repwise.example.com",
        })
        assert captured["is_secure"] is True
        assert captured["url"] == "https://repwise.example.com/"


class TestSqliteJournalMode:
    @pytest.mark.parametrize("raw, expected", [
        (None, "WAL"),
        ("delete", "DELETE"),
        ("WAL", "WAL"),
        ("truncate", "WAL"),
        ("", "WAL"),
    ])
    def test_journal_mode_env_parsing(self, monkeypatch, raw, expected):
        """PythonAnywhere needs DELETE; anything unrecognized falls back to
        WAL rather than passing arbitrary text into a PRAGMA."""
        from app import _sqlite_journal_mode
        if raw is None:
            monkeypatch.delenv("SQLITE_JOURNAL_MODE", raising=False)
        else:
            monkeypatch.setenv("SQLITE_JOURNAL_MODE", raw)
        assert _sqlite_journal_mode() == expected


class TestZeroTokenRule:
    def test_no_ai_sdk_in_requirements(self):
        """PLAN.md's zero-token rule: core features never call an LLM.
        An AI SDK showing up in requirements.txt should be a deliberate
        Phase 10 decision, so update this test when that happens."""
        from pathlib import Path
        reqs = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
        for sdk in ("openai", "anthropic", "google-generativeai", "langchain"):
            assert sdk not in reqs.lower()
