# The Idea Stage

A clean, guided web app that walks a founder through validating (or first
generating) a startup idea, following the *founders playbook*. You move through
five stages — **hypothesis → market → discovery → outreach → solution** — and after
each one a **Coach** explains in plain language what was found, what it means, what's
strong, and what's risky, so *you* decide whether to continue. No scores, no
elimination — the founder drives.

> Status: **Phase 1** complete — the core validation engine + a thin UI, runnable
> end-to-end locally (mock + live). Auth, profiles, ideation, payments, and deploy
> come in later phases (see `/Users/adityapeela/.claude/plans/`).

## Layout

```
engine/   Python package — Anthropic client, skill prompt modules, the 5 stages,
          the Coach, typed Pydantic handoffs, deterministic mock mode.
api/      FastAPI service — runs + Server-Sent-Events progress (no auth yet).
web/      Next.js app (App Router, Tailwind v4) — the run-journey UI.
old/      The previous CLI "gauntlet" (reference only; not shipped).
```

## Architecture

- **`engine/client.py::run_agent` is the single Anthropic chokepoint.** Every stage
  sub-role and the Coach go through it: it builds one Messages call from a `Role`
  (system prompt + scoped skill modules, prompt-cached), an output tool whose schema
  is the target Pydantic model, and — for research roles — the web-search tool. In
  mock mode it returns deterministic schema-valid objects with zero API calls.
- **Typed handoffs only.** Each stage returns a Pydantic object; the next stage
  receives only that object (`engine/models.py`).
- **The Coach replaces scoring** (`engine/coach.py` + `engine/skills/stage-coach.md`):
  it produces a `StageReview` (summary, strengths, risks, playbook flags, advice).
- **Orchestration is plain Python, one stage at a time** (`engine/conductor.py`).
  The API/UI holds the chain and asks for the next stage when the user continues.

Model split: stages on `claude-opus-4-8`, Coach on `claude-haiku-4-5`.

## Run it locally

```bash
# Python (engine + api)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Offline smoke test (zero API calls)
pytest

# Step through a journey in the terminal (mock = offline)
python -m engine --mock --auto --idea "AI expense reconciliation for finance teams"

# API (terminal 1)
uvicorn api.main:app --port 8000 --reload

# Web (terminal 2)
cd web && npm install && npm run dev   # http://localhost:3000
```

For live runs, export `ANTHROPIC_API_KEY` and untick "Mock mode" in the UI (or drop
`--mock` in the CLI). Copy `.env.example` for the full variable list.
