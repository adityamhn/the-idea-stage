# CLAUDE.md

Guidance for working in this repo. The full phased build plan lives at
`/Users/adityapeela/.claude/plans/we-are-fully-updating-woolly-kahn.md`.

## How to think (read first)

Build this as if **Paul Graham (YC), a16z, or Sequoia partners use it to validate a
founder.** Adopt the stance of a sharp, fair, experienced VC / domain expert — never a
cheerleader. The bar is evidence, not enthusiasm.

- **Every external fact shows a clickable citation.** Hypotheses, pressure-test points,
  competitor claims, market figures, trends — each material claim carries a real source
  (URL + title + quoted snippet) the user can verify. **Never fabricate a URL.** If
  something is an inference rather than a sourced fact, label it as reasoning — don't
  dress it up as evidence.
- Validate honestly: surface disconfirming evidence as eagerly as supporting evidence.

## Coding rules (binding)

1. **Closed-loop verification — verify every feature right after building it.** Run it,
   hit the endpoint, drive the UI in the preview, check the real output. Do not move on
   from a feature until you've observed it working end-to-end. "Looks done" is not done.
2. **Production quality.** Write code worthy of the users above — correct, observable,
   handling the cases that are real. No throwaway shortcuts.
3. **Simple code.** The minimum that solves the problem. No speculative abstractions,
   config, or fallbacks that weren't asked for.
4. **Mock mode stays green** (`pytest`, offline, zero API calls) after every change.

## What this is

**The Idea Stage** — a deployable web app that guides a founder through validating
(or generating) a startup idea on the *founders playbook*. Five stages with a
plain-language **Coach** between each. **No scoring, no elimination** — progression
is user-driven. This is a from-scratch rebuild; the old CLI "gauntlet" is archived
in `old/` (reference only).

## Architecture

```
web (Next.js)  ──HTTP/SSE──>  api (FastAPI)  ──>  engine (Python + Anthropic API)
```

- **`engine/client.py::run_agent` is the ONE Anthropic chokepoint.** Route every
  model call through it. It builds a single Messages call from a `Role`
  (`engine/roles.py`): system prompt + scoped skill modules (`engine/skills/*.md`,
  prompt-cached), a structured-output tool whose schema is the target Pydantic model
  (`engine/models.py`), and the web-search tool for research roles. `config.mock`
  short-circuits to `engine/mock.py` — deterministic, schema-valid, zero API calls.
- **Typed handoffs only** (`engine/models.py`): `ValidatedHypothesis → MarketAssessment
  → DiscoveryPlan → OutreachResults → SolutionConcept`. Each model carries forward the
  recap downstream stages need; the next stage receives ONLY the previous object.
- **The Coach** (`engine/coach.py`, `skills/stage-coach.md`) returns a `StageReview`
  (summary, what-this-means, strengths, risks, `playbook_flags`, suggested_next).
  It is advisory — never a gate.
- **Orchestration is plain Python, one stage at a time** (`engine/conductor.py`):
  `run_stage(stage_key, prior, config)` runs the stage then the Coach. The caller
  (api `Run` in `api/store.py`, or `engine/cli.py`) holds the chain.
- **Playbook truth** lives in `engine/playbook.py` (goal, 3 exit criteria, 3 traps)
  and is injected into the Coach + surfaced in the UI onboarding.

## Invariants to preserve

1. **One chokepoint.** New model calls go through `run_agent`, never the Anthropic
   client directly — that's what keeps mock mode, usage metering, and caching working.
2. **Output-only handoffs.** A stage gets the previous stage's typed object as JSON,
   nothing else. Add a field a later stage needs to the model; don't smuggle context.
3. **Skill scoping.** A `Role.skills` lists ONLY the modules it should load; don't
   widen it (e.g. `stage-coach` must not leak into a stage worker).
4. **No scoring / no elimination.** Never reintroduce a pass/fail gate. The Coach
   explains; the user decides.
5. **Mock mode stays green.** `pytest` runs the whole journey offline with zero API
   calls — keep `engine/mock.py` in sync when models change.

## Commands

```bash
pip install -e ".[dev]"
pytest                                              # offline smoke test
python -m engine --mock --auto --idea "..."         # CLI journey (offline)
uvicorn api.main:app --port 8000 --reload           # API
cd web && npm run dev                               # frontend (localhost:3000)
```

Live runs need `ANTHROPIC_API_KEY`; everything else runs in mock mode.

## Stack decisions (locked)

Direct Anthropic API (not the Agent SDK) · Supabase for auth/Postgres/storage (Phase 2+)
· Razorpay credit packs metered by token usage (Phase 5) · Stage 4 = drafts + scheduling
link only, no auto-send · web → Vercel, api → Railway.
