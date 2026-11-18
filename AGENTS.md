# AGENTS.md — onboarding for AI coding agents

If you're an AI agent working in `project-rep-wise`, read this first, then
`PLAN.md`.

## Boundary — this is a personal project

This repo is **not** Nike work. Drop any carried-over Nike context, rules,
terminology, or frameworks. Just a hobby Flask app.

Git author: `Zachariah Phillips <zachariah.r.phillips@gmail.com>` → GitHub
`@zachariahphillips` (personal). Never commit or push under a work identity.

## What it is (1-liner)

Flask + htmx + SQLite mobile-first workout app that builds a training plan
from the user's goals, logs workouts, and adapts the plan over time.

## The zero-token rule

**Core features never call an LLM.** Plan generation, progression, PRs,
stall detection, rescheduling, stats, and charts are deterministic Python.
The app must work fully with no AI API key set. Optional AI features are a
Phase 10 decision with per-user caps and cached results (see `PLAN.md`).
`tests/test_phase_0.py::TestZeroTokenRule` fails if an AI SDK appears in
`requirements.txt`; changing that is a deliberate decision, not a drive-by.

## Local dev

```bash
source .venv/bin/activate         # system Python 3.9 locally; CI runs 3.12
npm ci                            # Tailwind CLI, only when changing CSS/classes
npm run build:css                 # rebuild committed static/css/app.css
python app.py                     # http://127.0.0.1:5002
pytest -q                         # full regression
```

Port 5002 is intentional: Pawsitive Coach uses 5000, PantryPal uses 5001.

Code must stay **Python 3.9 compatible** (`from __future__ import
annotations`, `Optional[...]` instead of `X | None` at runtime).

## Repo layout

| Path | What lives there |
|---|---|
| `app.py` | App factory, config guards, routes. |
| `extensions.py` | `db`, `csrf` singletons. |
| `templates/` | Jinja. `_partial.html` files will be htmx swap targets. |
| `assets/css/app.css` | Tailwind entry; compiled to `static/css/app.css` (committed). |
| `tests/conftest.py` | CSRF-aware `Client` wrapper, per-test SQLite file. |
| `tests/test_phase_XX.py` | One file per phase. |
| `PLAN.md` | Roadmap, plan-builder rules, data model. |
| `planner/` | (Phase 5B) Pure-Python plan generator. No Flask or DB imports. |

## Development workflow

Work happens in **phases** from `PLAN.md`. Each phase:

1. **Plan** — confirm scope against the `PLAN.md` section.
2. **Implement.**
3. **Test** — add `tests/test_phase_XX.py`; docstrings say what each test
   guards and why.
4. **Run** — `pytest tests/test_phase_XX.py -v`, then full `pytest -q`.
5. **Visual verify (UI phases)** — local server + Chrome DevTools MCP at
   390×844. Screenshots go in `/tmp/`, never committed.
6. **Update `PLAN.md`** — mark the phase done with a short summary.
7. **Commit** — `Phase XX: <short description>`, push to `main` (single-dev
   repo, no PR flow).

Bump `APP_PHASE` in `app.py` when a phase ships.

## Code conventions

- Comments explain constraints the code can't show, not what the next line does.
- Tests carry docstrings explaining what they guard.
- No new dependencies without a reason; pin them in `requirements.txt` with a comment.
- Weights are stored **with their unit** per set; convert only for display.

## Gotchas inherited from PantryPal

- **CSRF is on in tests.** Use the `Client` wrapper; a 400 on POST usually
  means a missing token.
- **`db.create_all()` only creates missing tables, never columns.** Adding a
  column to an existing table needs an explicit, idempotent `ALTER TABLE`.
- **SQLite URLs:** 4 slashes = absolute path, 3 = relative to `instance/`.
- **gunicorn `--workers=1`** while on SQLite.
- **Stop the dev server before wiping or migrating the DB** — debug
  auto-reload runs `create_app()` on every save.
- **ProxyFix only applies through `test_client()`,** not `test_request_context`.

## Fresh-clone git-identity pin

```bash
git config --local --replace-all credential.https://github.com.helper ""
git config --local --add credential.https://github.com.helper \
  '!f() { test "$1" = "get" && printf "username=zachariahphillips\npassword=%s\n" "$(gh auth token --user zachariahphillips -h github.com)"; }; f'
```
