# RepWise — Build Plan

A mobile-first workout app that **builds you a training plan from your goals**, then becomes the logbook you use on the gym floor — and adjusts the plan as you get stronger.

**Current status (Phase 1C1, 2026-11-25):** Skeleton plus email/password auth: signup with a lb/kg preference, login with remember-me and safe `?next=` redirects, POST-only logout, and a signed-in `/today` placeholder. Phase 1B added the exercise model, a 64-exercise library with coverage guarantees, and the `/exercises` browse/search/detail screens with a bottom tab bar. Phase 1C1 added workouts: start / resume / finish / discard from Today, with the finish rules enforced server-side. 229 pytest tests green. Next is Phase 1C2 (logging sets).

---

## Vision

Answer six questions (goal, experience, days per week, time per session, equipment, limitations) and get a sensible multi-week program. Each day, open the app, tap "Start workout," and log sets with the numbers already pre-filled from last time. The app celebrates PRs, tells you when to add weight, notices when you've stalled, and reshuffles when you miss a day.

It should feel like a coach that knows the rules — not a chatbot.

## The zero-token rule (non-negotiable)

**Every core feature runs on deterministic Python. The app must be fully functional with `OPENAI_API_KEY` unset.**

- Plan generation, progression, PR detection, stall detection, rescheduling, stats, and charts are all rules + math. No LLM calls.
- AI features (Phase 10, optional) must be: user-triggered (never automatic on page load), rare (≈ once per plan or once per month), capped per user per day, and cached in the DB so the same answer is never paid for twice.
- Tests never hit a real AI API. If a phase adds an AI call, it also adds a `/cost` line item and a daily cap — the PantryPal Phase 3C pattern.

Using AI to *build* the app is fine. The app itself spending tokens on routine work is not.

## Locked decisions

| Decision | Choice | Why |
|---|---|---|
| **Name** | RepWise (working name) | Easy to change before Phase 0 pushes to GitHub |
| **Folder + repo** | `project-rep-wise` | Matches the `project-*` convention |
| **Backend** | Python + Flask, app-factory pattern | Same stack as PantryPal and Pawsitive Coach |
| **Database** | SQLite (WAL mode) | Zero infra; same hardening patterns as PantryPal |
| **Auth** | Flask-Login + Werkzeug pbkdf2 | Copy PantryPal's Phase 1A almost verbatim |
| **UI** | Jinja + htmx + compiled Tailwind CLI | Same as PantryPal's end state (skip the CDN phase) |
| **Charts** | Decide at Phase 5 (server-rendered SVG vs. one small vendored JS lib) | Avoid a dependency until it's needed |
| **Hosting** | PythonAnywhere free tier | Same no-cost path PantryPal settled on |
| **Port** | 5002 | 5000 = Pawsitive Coach, 5001 = PantryPal |
| **Units** | lb default, per-user kg toggle | Store each set's weight **with its unit**; convert only for display |
| **Multi-user** | Solo accounts (no households) | Training data is personal; sharing can come later |

---

## Phased build — each phase ends at a useful state

Every phase follows the PantryPal workflow: plan → implement → `tests/test_phase_XX.py` → full `pytest -q` → mobile-viewport visual check for UI phases → commit `Phase XX: <description>`.

### Phase 0 — Setup (1 sitting) — DONE 2026-11-18

- `git init`, `.gitignore`, `.env.example`, `requirements.txt` (pinned, with comments)
- `AGENTS.md` (adapted from PantryPal's: personal-project boundary, git identity pin, workflow, zero-token rule)
- Hello-world Flask app factory on `localhost:5002`, `/healthz` returning the phase
- `tests/conftest.py` with the CSRF-aware `Client` wrapper copied from PantryPal
- Tailwind CLI build (`npm run build:css`) from day one
- GitHub Actions running `pytest -q` on push

**End state:** project exists, runs, tests run in CI, on GitHub.

### Phase 1 — Foundation: log a workout

#### 1A — Auth (1 sitting) — DONE 2026-11-19
- Signup / login / logout, `User` model, CSRF, safe `?next=` handling (port PantryPal's `_is_safe_next_url` and the production `SECRET_KEY` guard)

Shipped:
- `User` model (`models.py`) with pbkdf2 password hashing, `unit_pref` (`lb`/`kg`, chosen at signup as two big toggle buttons), and a `first_name` helper
- `SignupForm` / `LoginForm` (`forms.py`); name and email are whitespace-stripped *before* validation, because phone autocomplete adds trailing spaces and the `Email()` validator rejected them (caught by `test_email_is_normalized`)
- Emails are lowercased; unknown email and wrong password share one error message so the form doesn't reveal which emails have accounts
- Remember-me defaults on (phone-first); logout is POST-only
- `/` shows the landing page when signed out and redirects to `/today` when signed in; `/today` is a placeholder until Phase 1C
- Shared `_macros.html` (`text_field`, `primary_button`), flash messages, and a header with Sign out in `base.html`; dark mode throughout
- `tests/test_phase_1a.py` — 29 cases; `conftest.py` gains `sign_up` / `log_in` / `log_out` helpers and a `two_clients` fixture
- Visual check at 390×844: signup → kg selected → lands on Today with welcome flash

#### 1B — Exercise library (split into three 1-sitting chunks)

Split so the tag vocabulary is settled on a small data set before 60 exercises depend on it. Filters and custom exercises moved after 1C (as 1D and 1E) so real workout logging arrives sooner.

##### 1B1 — Exercise model + tag vocabulary (1 sitting, no UI) — DONE 2026-11-20
- `Exercise` model (see "Data model"), with `is_custom` / `owner_user_id` columns present from the start even though 1E is what uses them
- Controlled vocabularies as module constants: movement patterns, muscles, equipment, stresses (see "Exercise library")
- `seed_exercises.py`: idempotent upsert keyed on `slug`, safe to re-run against a live DB
- ~15 core lifts (squat, bench, deadlift, row, overhead press, pull-up, lunge, RDL, etc.)
- Tests: every seeded tag is in its vocabulary, slugs are unique, re-running the seed changes nothing

Shipped:
- `exercise_vocab.py`: movement patterns, muscles, equipment, stresses, the four equipment profiles, `fits_equipment()`, and `validate_exercise()`. No Flask/DB imports (pinned by an AST-based test) so the 5B generator and 1E form can share it
- `Exercise` model with JSON list columns for muscles/equipment/stresses; `increment_lb` / `increment_kg` replace the single `default_increment` (both NULL = progress by reps, e.g. push-ups and pull-ups)
- `seed_exercises.py` with 15 core lifts covering all seven main movement patterns; runs on every `create_app()` so deploys pick up library edits automatically. Updates rows in place (ids stable for logged sets), never deletes, never touches custom exercises, and refuses to boot on invalid seed data
- Validation caught one real bug during testing: `difficulty: True` passed because Python's `bool` is an `int`
- `tests/test_phase_1b1.py` — 44 cases

##### 1B2 — Fill out the library (1 sitting, data only) — DONE 2026-11-23
- Grow to ~60 exercises so every movement pattern has options for each equipment profile (full gym, home gym, dumbbells only, bodyweight only)
- Coverage test: every movement pattern × equipment profile has at least one exercise. This is the guarantee Phase 5's generator relies on

Shipped:
- Library data moved to `exercise_library.py` (one compact `_ex(...)` row per exercise); `seed_exercises.py` is now logic only. The original 15 lifts are unchanged, so no existing rows are rewritten
- 64 exercises across all 11 movement patterns, including isolation moves tagged `is_compound=False` so the generator can prefer compounds for main slots
- Two explicit coverage gaps, listed in `KNOWN_GAPS` in the test: **vertical pull for dumbbells-only and bodyweight**. There's nothing overhead to pull from, so the 5B generator must fall back to a horizontal pull there. The test fails if a gap gets filled without the list being updated
- Also guaranteed: ≥2 compound options per main pattern in a full gym (for 5C swaps), every vocabulary value is used by at least one exercise, and in a full gym each core pattern has an option avoiding each stress (except squats and knees, where the generator substitutes a hinge)
- `tests/test_phase_1b2.py` — 81 cases

##### 1B3 — Browse + search (1 sitting) — DONE 2026-11-24
- `/exercises` grouped by movement pattern, search by name, simple detail view (muscles, equipment, stresses)
- Bottom tab bar (Today / Exercises), same safe-area pattern as PantryPal
- The search becomes the exercise picker 1C reuses

Shipped:
- `/exercises`: groups in vocabulary order (main lifts first), alphabetical within each group; each row shows equipment (or "Bodyweight") and main muscles
- Search matches every word against name **and** tags, so "dumbbell chest" narrows and "lower back" matches the `lower-back` tag. Live via htmx (200 ms debounce, URL kept in sync with `hx-replace-url`), and still works as a plain GET form without JavaScript. Results render from `_exercise_list.html`, the swap target 1C's picker will reuse
- htmx history restores get the full page (they send `HX-Request` too), so Back after a search doesn't render a bare fragment
- `/exercises/<slug>`: main vs secondary muscles, equipment, a "go easy if you have issues with" stress section, and progression in the user's unit ("Add 2.5 kg…", or "add reps" for bodyweight moves)
- Visibility helper `_visible_exercises_query()`: global exercises plus your own custom ones; another user's custom exercise is hidden from the list and search, and 404s on its detail page
- `exercise_vocab.label()` and `DIFFICULTY_LABELS` for display text
- Fixed bottom tab bar (Today / Exercises) with `aria-current` and iPhone safe-area padding
- `tests/test_phase_1b3.py` — 30 cases. Visual check at 390×844: list, live "dumbbell chest" search, and squat detail

#### 1C — Freeform workout logging (split into three 1-sitting chunks)

Behavior decisions (2026-11-24):
- **Finish keeps every set with a weight and reps**, checked or not; rows missing either are dropped. Exception (1C1): rep-progressed exercises (no plate increment, e.g. push-ups, pull-ups) only need reps. Exercises left with no sets are dropped too
- **Open workouts are never auto-finished.** Today shows "Resume workout" with finish / discard options, however long it's been
- **Finishing with no kept sets is a discard**, so history never fills with empty workouts
- **Exercises stay in the order added**; reordering is a later nicety
- Only one in-progress workout per user at a time

##### 1C1 — Workout lifecycle (1 sitting) — DONE 2026-11-25
- `Workout` and `WorkoutSet` models (see "Data model"); sets store weight **with its unit** and a client-generated `client_id` for Phase 9's idempotent offline sync
- Start (`POST`), discard, and finish routes; starting while one is open resumes it instead of creating a second
- Today: "Start empty workout" when idle, "Resume workout" card (started time, exercise/set counts) when one is open
- The finish rules above, enforced server-side and tested

Shipped:
- `Workout`, `WorkoutExercise`, `WorkoutSet` models. `WorkoutExercise` is new versus the first-cut data model: it holds an exercise's place in the workout before any sets exist, which the "order added" rule needs
- A partial unique index (`user_id WHERE finished_at IS NULL`) backstops "one open workout per user"; a racing second Start falls back to resuming
- `POST /workouts/start`, `GET /workouts/<id>` (read-only active screen until 1C2), `POST /workouts/<id>/finish`, `POST /workouts/<id>/discard` (with a confirm). Someone else's workout, or a finished one, is a 404
- Finish logic lives in `WorkoutSet.is_logged` and `Workout.prune_unlogged()`; `program_day_id` / `template_id` are deferred to the phases that add those tables
- Today tab stays highlighted on the workout screen; `relative_time` Jinja filter ("just now", "3 days ago")
- `tests/test_phase_1c1.py` — 30 cases. Visual check at 390×844: idle Today, resume card, active screen, finish flash

##### 1C2 — Logging sets (1 sitting)
- Active workout screen: add exercises with the 1B3 picker (`_exercise_list.html`), then add / edit / delete sets via htmx
- Big thumb-friendly inputs with numeric keypads (`inputmode="decimal"` for weight, `numeric` for reps); weight defaults to the user's unit
- Remove an exercise from the workout (and its sets)

##### 1C3 — History (1 sitting)
- `/history`: finished workouts, newest first, with date, duration, and exercise / set counts
- `/history/<id>`: every exercise and set; edit or delete a set after the fact
- Delete a whole past workout (with confirm)
- Strict per-user isolation: other users' workouts 404

#### 1D — Exercise filters (1 sitting)
- Tap-to-filter chips for equipment and muscle group on `/exercises` and in the picker

#### 1E — Custom exercises (1 sitting)
- Create / edit / delete your own exercises (`is_custom`, `owner_user_id`), visible only to you
- Custom exercises must pick tags from the same vocabularies so the planner can use them later
- Deleting a custom exercise that has logged sets: block it, or archive instead of delete (decide at 1E)

**End state:** a working (if plain) lift log you can use on your phone.

### Phase 2 — Deploy (1 sitting)

Ship early so real gym use drives the rest of the roadmap.

- PythonAnywhere deploy using PantryPal's runbook, preflight helper, and backup scripts
- `/healthz` DB check, production cookie flags, `ProxyFix`
- PWA manifest + icons so it installs to the home screen (offline comes in Phase 8)

**End state:** RepWise on a public URL, installed on your phone.

### Phase 3 — "Last time" and PRs (1–2 sittings)

- Each exercise in the active workout shows last session's sets ("Last: 175 × 8, 8, 7")
- New sets pre-fill from last time's weight and reps
- PR detection on finish: heaviest weight, best estimated 1RM, most reps at a given weight
- PR toast + a PR badge in history

**End state:** the app is noticeably better than a notes app.

### Phase 4 — Templates (1 sitting)

- Save a finished workout as a template; build templates by hand
- "Start from template" pre-loads exercises + target sets/reps
- This is the data shape the plan generator will produce in Phase 5

**End state:** repeatable routines without retyping.

### Phase 5 — Plan builder v1 (the headline feature, 3–4 sittings)

#### 5A — Goals questionnaire
- Mobile-friendly, one-question-per-screen onboarding (skippable — freeform logging still works)
- Stores a `TrainingProfile` per user; editable later
- Short health disclaimer before the first plan ("not medical advice; check with a doctor if you have injuries or conditions")

#### 5B — Generator engine (pure Python, no Flask imports)
- `planner/` package: `profile → Program` as a pure function, heavily unit-tested
- Rules described in "Plan builder rules" below
- Same inputs always produce the same plan (seeded choice when picking among equally good exercises)
- Every generated plan stores a snapshot of the inputs + a `rules_version` so old plans stay explainable after the rules change

#### 5C — Plan view + start from plan
- `/plan`: week-by-week schedule, today's session highlighted, where you are in the cycle
- "Start today's workout" pre-loads the planned exercises, sets, reps, and suggested weights
- Swap an exercise for an equivalent one (same movement pattern, allowed equipment)
- "Why this plan" panel built from templated text explaining each rule that fired (no AI)

**End state:** answer six questions, get a real program, train from it.

### Phase 6 — Charts and progress (1–2 sittings)

- Per-exercise chart: best set and estimated 1RM over time
- Weekly volume per muscle group
- Consistency heatmap (calendar of sessions)
- Plan adherence ("Week 3 of 8 — 7 of 9 sessions done")

### Phase 7 — Adaptive plans (2 sittings)

- Progression suggestions applied to the next session's target weight (see rules below)
- Stall detection → suggest a deload
- Missed-day handling: the next workout becomes the missed one; the plan shifts rather than skipping
- End-of-cycle prompt: "Plan finished — regenerate with the same goals, or change them?"
- All suggestions are **accept / reject**, never silently applied

### Phase 8 — Gym-floor UX (2 sittings)

- Rest timer that starts when a set is checked off (vibration where supported)
- Plate calculator ("185 lb = 45 bar + 45 + 25 per side"), configurable bar and plates
- Big-thumb layout, numeric keypads (`inputmode="decimal"`), Screen Wake Lock during workouts
- Dark mode
- Target: logging a set takes ≤ 2 taps when the pre-fill is right

### Phase 9 — Offline logging (2–3 sittings, the hardest phase)

- Service worker caches the app shell
- Sets logged offline queue in IndexedDB and sync when back online
- Conflict rule: client-generated set IDs make sync idempotent (a retry never duplicates a set)

### Phase 10 — Optional AI (only if wanted; respect the zero-token rule)

Candidates, each one call per user action, capped and cached:
- **Paste a program → template**: turn text from Reddit or a PDF into a structured template
- **Free-text goal → profile**: "I want to dunk by summer" → structured questionnaire answers the user confirms
- **Monthly recap**: a short paragraph summarizing the month, generated on request

### Later / à la carte

Body weight + measurements, CSV export/import (Strong / Hevy formats), supersets, RPE/RIR logging, cardio sessions, advanced periodization, sharing a plan with a friend.

---

## Plan builder rules (v1)

The generator works in **slots**: each training day is a list of movement-pattern slots, and each slot is filled from the exercise library.

### 1. Days per week → split

| Days | Split | Day structure |
|---|---|---|
| 2 | Full body A/B | Each day: squat or hinge, push, pull, accessory |
| 3 | Full body A/B/C (beginner) or Upper/Lower/Full (intermediate) | Rotating patterns |
| 4 | Upper/Lower × 2 | Upper: horizontal push, horizontal pull, vertical push, vertical pull, arms. Lower: squat, hinge, single-leg, calves/core |
| 5 | Upper/Lower + Push/Pull/Legs | Mixed |
| 6 | Push/Pull/Legs × 2 | PPL |

### 2. Goal → sets, reps, rest

| Goal | Main lifts | Accessories | Rest | Extras |
|---|---|---|---|---|
| Strength | 3–5 × 3–6 | 3 × 8–10 | 2–4 min | Compound-heavy slot order |
| Muscle | 3–4 × 6–10 | 3 × 10–15 | 1–2 min | More accessory slots |
| Fat loss / general | 3 × 8–12 | 2–3 × 12–15 | 60–90 s | Optional conditioning finisher |
| Endurance | 2–3 × 12–15 | 2 × 15–20 | 30–60 s | Circuit-style pairing |

### 3. Experience → progression model

| Level | Model | Rule |
|---|---|---|
| Beginner (< 6 months) | Linear | All target reps hit → +5 lb upper body / +10 lb lower body next session |
| Intermediate | Double progression | Work up through the rep range; when the top of the range is hit on all sets → add weight, drop to the bottom of the range |
| Advanced | Deferred | v1 treats advanced as intermediate; real periodization is a "Later" item |

kg users get +2.5 / +5 kg. Increments round to the user's smallest available plate pair.

### 4. Session length → slot count

| Minutes | Exercises per session |
|---|---|
| 30 | 3–4 |
| 45 | 4–5 |
| 60 | 5–6 |
| 90 | 6–8 |

### 5. Equipment + limitations → exercise filter

- Exercises need every piece of equipment they're tagged with to be available
- Limitations exclude exercises tagged with that stress (e.g. "lower back" excludes conventional deadlifts and good mornings, keeps hip thrusts and leg curls)
- If a slot can't be filled, fall back to the closest movement pattern; if still empty, drop the slot and say so in "Why this plan"

### 6. Adaptation (Phase 7)

- **Stall:** missed target reps on the same exercise 3 sessions in a row → suggest a 10% deload, then resume progression
- **Missed day:** the next session is the missed one; the program end date moves out
- **Starting weights:** first session for each exercise is "find your working weight" (log what feels like ~2 reps in reserve); progression starts from there

---

## Exercise library

Seeded from `seed_exercises.py` (idempotent, keyed on `slug`). Target ~60 exercises for v1, covering every movement pattern with options for each equipment profile.

Each exercise is tagged with:

| Field | Example |
|---|---|
| `slug` | `barbell-back-squat` |
| `movement_pattern` | squat, hinge, single-leg, horizontal-push, vertical-push, horizontal-pull, vertical-pull, arms, core, calves, conditioning |
| `primary_muscles` / `secondary_muscles` | quads, glutes / hamstrings, core |
| `equipment` | barbell, rack, bench |
| `difficulty` | 1–3 |
| `is_compound` | true |
| `stresses` | knees, lower-back |
| `increment_lb` / `increment_kg` | 10 / 5 (both empty for bodyweight moves that progress by reps) |

Equipment profiles offered in the questionnaire: full gym, home gym (barbell + rack + dumbbells), dumbbells only, bodyweight only, custom.

---

## Data model (first cut)

```text
users
  id, email, password_hash, name, unit_pref ("lb"|"kg"), created_at

exercises
  id, slug (unique), name, movement_pattern, primary_muscles (json),
  secondary_muscles (json), equipment (json), difficulty, is_compound,
  stresses (json), increment_lb, increment_kg (both null = progress by reps),
  is_custom, owner_user_id (null = global)

training_profiles                                   -- Phase 5A
  id, user_id (unique), goal, experience, days_per_week, minutes_per_session,
  equipment (json), limitations (json), updated_at

programs                                            -- Phase 5B
  id, user_id, name, status ("active"|"finished"|"abandoned"),
  inputs_snapshot (json), rules_version, start_date, weeks, created_at

program_days
  id, program_id, position, name ("Upper A")

program_slots
  id, program_day_id, position, exercise_id, movement_pattern,
  sets, rep_min, rep_max, rest_seconds, progression_model, target_weight, target_unit

templates                                           -- Phase 4
  id, user_id, name, created_at
template_exercises
  id, template_id, position, exercise_id, sets, rep_min, rep_max, rest_seconds

workouts
  id, user_id, program_day_id (nullable), template_id (nullable),
  started_at, finished_at (null = in progress), notes

  -- unique open workout per user: (user_id) WHERE finished_at IS NULL

workout_exercises                                   -- 1C1
  id, workout_id, exercise_id, position

workout_sets
  id, client_id (uuid, unique — for idempotent offline sync), workout_exercise_id,
  position, weight, unit, reps, completed, is_warmup, logged_at

progression_suggestions                             -- Phase 7
  id, user_id, program_slot_id, kind ("increase"|"deload"|"hold"),
  from_weight, to_weight, unit, reason, status ("pending"|"accepted"|"rejected"), created_at
```

PRs are **derived** from `workout_sets` at query time in v1. Add a cache table only if it gets slow.

---

## Why this build order

- **Logger before planner.** Generated plans need somewhere to live. The logger is useful by itself and gets you real data to test the planner against.
- **Deploy at Phase 2.** A gym app is only real when it's on your phone at the gym. Early real use beats speculative features.
- **Templates before the generator.** The generator's output *is* a template with more structure. Building templates by hand first proves the data shape.
- **Generator as a pure Python package.** No Flask, no DB in `planner/`. That makes it the most testable part of the app and the most fun to iterate on.
- **Offline last-ish.** It's the hardest phase and the app works fine without it on decent gym Wi-Fi.

---

## Open questions (answer at the phase they affect)

1. ~~**Final name**~~ — RepWise, decided 2026-11-18.
2. **Charts** — server-rendered SVG vs. a vendored lightweight library. Phase 6.
3. **Advanced lifters** — real periodization or keep treating them as intermediate? After Phase 7, based on actual use.
4. **Warm-up sets** — auto-generate warm-up ramps or let the user log them freely? Phase 8.
5. **Rules sources** — which well-known programs to model the templates after (e.g. a 3-day beginner linear program, a 4-day upper/lower). Phase 5B.

---

## Reference repos

- `../project-pantry-pal` — the playbook. Reuse: app factory, auth, CSRF test client, SQLite hardening, PythonAnywhere deploy + backup scripts, PWA manifest, Tailwind CLI build, toast/undo patterns, the phase/test workflow, and (only if Phase 10 happens) the OpenAI cost-guardrail pattern.
- `../project-pawsitive-coach` — the original Flask skeleton.
