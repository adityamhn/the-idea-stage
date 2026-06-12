# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A gated, multi-agent "gauntlet" that validates startup ideas, built on the **Claude Agent SDK** (`claude-agent-sdk==0.2.87`, pinned — the SDK API moves). Many ideas go in; each runs through 5 sequential stages with an adversarial **gate** between every stage. Fail a gate → eliminated; reach and pass stage 5 → winner, ranked by summed gate score.

The package is `idea_gauntlet` under `src/`. The README is the authoritative product doc; this file covers the architecture and the non-obvious invariants you must preserve.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # or: uv pip install -e ".[dev]"

# Run offline (deterministic, zero API calls) — use this for nearly all dev:
python -m idea_gauntlet --mock --ideas ideas.txt

# Live run (needs ANTHROPIC_API_KEY exported):
python -m idea_gauntlet --ideas ideas.txt
python -m idea_gauntlet --retries 2 "AI expense reconciliation for finance teams"

# Tests
pytest                              # offline smoke test (mock mode)
pytest tests/test_smoke.py::test_ranking_is_descending_for_winners   # single test
python tests/test_smoke.py          # runs without pytest installed
```

There is no linter/formatter configured. Runs write to `runs/run-YYYYMMDD-HHMMSS/` unless `--no-save`.

## Architecture: the layered flow

```
cli.py → conductor.run_gauntlet → conductor.run_idea (per idea)
           → PIPELINE: [stage_fn, gate] × 5  (stages.py + gates.py)
              → run_agent (runner.py)  ← THE single SDK/mock chokepoint
```

- **`runner.py::run_agent` is the one and only primitive.** Every stage sub-role and every gate goes through it. It either dispatches to the SDK or, when `config.mock`, to `mock.py::mock_dispatch` — so the whole pipeline runs offline with no SDK installed (the SDK is imported lazily *inside* `run_agent`). If you add a new agent call, route it through `run_agent`; don't call `query()` directly.
- **`conductor.py` is plain deterministic Python — no LLM in the orchestration loop.** It runs ideas concurrently (bounded by `asyncio.Semaphore`), applies gates, handles retries, eliminates losers (raising `Eliminated`), and ranks winners. Keep orchestration logic here, not in stages.
- **`stages.py`** holds the 5 stage functions. Each is `async (prev_typed_output, config, feedback) -> next_typed_output`. Stages contain NO gate logic. Stage 1 runs two sub-agents sequentially; stage 2 runs three analysts in parallel via `asyncio.gather` then synthesizes.
- **`agents.py`** declares one `RoleSpec` per sub-agent (system prompt, allowed skills, tools, gate-or-stage). `runner` turns a `RoleSpec` into an SDK `AgentDefinition` at call time.
- **`gates.py`** is the adversarial judge — one per stage boundary, on the fast model, loading the `gate-rubric` skill. The gate returns a `GateVerdict`; the *conductor*, not the gate, decides proceed/retry/eliminate.

## Invariants you must not break

1. **Context isolation is structural, not stylistic.** Each `run_agent` call is a fresh `query()` that registers exactly one subagent and invokes it explicitly. The ONLY thing crossing the boundary is the `prompt` string. A downstream stage must receive only the previous stage's **typed Pydantic object** — never upstream chat/reasoning. This is the core design property; preserve it.
2. **Typed handoffs only.** Stage boundaries are Pydantic models in `models.py` (`ValidatedHypothesis → MarketAssessment → DiscoveryPlan → OutreachResults → SolutionConcept`), returned via the SDK's structured outputs (`output_format={"type":"json_schema",...}`). Because each model is the sole channel forward, it must carry a compact recap of upstream essentials downstream stages need (e.g. `hypothesis_recap`). When you add a field a later stage depends on, thread it through the model — don't smuggle it via prompt context.
3. **Skill scoping is a guard, not a hint.** Each `RoleSpec.skills` lists ONLY the skills that role may load, and `run_agent` sets the session-level `skills=[...]` filter to exactly that set. This prevents e.g. `gate-rubric` leaking into a stage worker. Skills load from the **filesystem only**, which is why `run_agent` sets `setting_sources=["user","project"]` and `cwd=project_root`. Don't widen a role's skills without reason.
4. **`"Agent"` must stay in `allowed_tools`** or subagent invocations fall through to the permission callback instead of auto-approving.
5. **The trace recorder is bound per-idea via a `ContextVar`** (`trace.py`). `run_idea` binds its own `IdeaRecorder`; `asyncio.gather` copies the context so concurrent ideas don't mix, while stage-2's parallel sub-agents inherit the same recorder and append to one ordered list. `run_agent` records every call. Keep `run_agent` as the recording chokepoint.

## Stage 4 is special — irreversible side effects

Stage 4 (outreach) sends real Gmail + creates real Calendar invites via **MCP**, and is a **pause/resume boundary** (waits days on human replies), so it is **OFF by default**: in `--mock` or without `--run-stage4` it returns a synthesized `OutreachResults(skipped=True)` so stages 5 still runs end-to-end. The live path:

- Pairs `run_agent` with `permissions.py::make_approval_hook` (`can_use_tool`): read-only/drafting tools auto-pass; anything that sends/creates/deletes prompts a human and is denied if unapproved. `--auto-approve-sends` removes that guard — treat it as genuinely dangerous.
- The MCP server config in `stages.py::_mcp_config` is a **placeholder** (`npx` stdio stubs) — point it at a real Gmail/Calendar MCP setup before using `--run-stage4`.

## Model split

Stages run on the strong model (`claude-opus-4-8`); gates run on the fast/cheap model (`claude-sonnet-4-6`). `run_agent` picks via `spec.is_gate`. Both overridable with `--stage-model` / `--gate-model`.

## Skills live in `.claude/skills/`

Six custom skills (`SKILL.md` each) plus the pre-built `xlsx` skill. Each is scoped to specific roles (see the table in README). `tam-sam-som` ships a **deterministic xlsx builder script** (`build_model.py`) that the sizing role runs — that role therefore gets `FILE_TOOLS` (Read/Write/Bash/Glob/Grep) plus the `xlsx` skill. If you edit a skill's exit criteria, the `gate-rubric` skill is what every gate scores against.
