# RepWise

A mobile-first workout app: answer a few questions about your goals, get a
training plan, then log your workouts against it. The plan adapts as you
get stronger. No AI calls are needed to run it.

See `PLAN.md` for the roadmap and `AGENTS.md` for development conventions.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # optional for local dev
python app.py                     # http://127.0.0.1:5002
pytest -q
```

CSS changes need the Tailwind CLI:

```bash
npm ci
npm run build:css                 # or: npm run watch:css
```
