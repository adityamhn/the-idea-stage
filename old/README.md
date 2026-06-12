# Idea Gauntlet

A gated, multi-agent **"gauntlet"** for validating startup ideas during the
**Idea stage** — built on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk).

Many candidate ideas go in. Each runs through **5 sequential stages**. An
**adversarial gate** sits between every stage and decides pass/fail. Ideas that
fail any gate are eliminated; ideas that reach and pass stage 5 are **winners**,
ranked by accumulated gate score.

```
idea ─▶ ① hypothesis ─[gate]─▶ ② market ─[gate]─▶ ③ discovery ─[gate]─▶ ④ outreach ─[gate]─▶ ⑤ solution ─[gate]─▶ WINNER
                 │                  │                   │                    │                    │
              eliminate          eliminate           eliminate            eliminate            eliminate
```

## Why it's shaped this way

- **Context isolation / output-only handoffs.** Each stage is an SDK **subagent**,
  so isolation is *structural*: a fresh context per call, only the prompt string
  in, only the final structured object out. Upstream reasoning never leaks
  downstream. (`runner.py`)
- **Typed handoffs.** Every stage boundary is a Pydantic model
  (`ValidatedHypothesis → MarketAssessment → DiscoveryPlan → OutreachResults →
  SolutionConcept`) returned via the SDK's **structured outputs**. Plus a
  `GateVerdict`. (`models.py`)
- **Orchestration is plain code.** A deterministic conductor runs ideas, applies
  gates, eliminates losers, handles retries and parallelism — no LLM in the loop.
  (`conductor.py`)
- **Gates are cheap and adversarial.** Each gate is an LLM-as-judge on a fast
  model, told to hunt for reasons NOT to proceed, scoring against exit criteria
  loaded from the `gate-rubric` skill. Stages run on a stronger model. Both are
  configurable. (`gates.py`, `agents.py`)

## Setup

```bash
cd idea-research-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # or:  uv pip install -e ".[dev]"

export ANTHROPIC_API_KEY=sk-ant-...   # only needed for live (non-mock) runs
```

The project pins `claude-agent-sdk==0.2.87` (Python ≥3.10).

## Run

```bash
# Offline, deterministic, zero API calls — great first run:
python -m idea_gauntlet --mock --ideas ideas.txt

# Live run (uses your API key):
python -m idea_gauntlet --ideas ideas.txt

# Ad-hoc ideas as args, with 2 evaluator-optimizer retries per gate:
python -m idea_gauntlet --retries 2 \
  "AI expense reconciliation for mid-market finance teams"
```

Output is a per-idea outcome line (winner / eliminated-at-stage-X-because-Y) plus
the ranked winners — and, unless you pass `--no-save`, a full record on disk.

### Saved records

Every run writes a timestamped directory (default under `runs/`) capturing
*everything*, so you can inspect the hypothesis, the research, the pressure test,
each gate's reasoning, and exactly why an idea died:

```
runs/run-YYYYMMDD-HHMMSS/
  report.md            overall report: summary table, ranked winners, eliminations
  report.json          machine-readable: every idea's complete record
  ideas/<slug>/
    idea.json          the full per-idea record (stage outputs + verdicts + trace)
    report.md          per-idea dossier (below)
```

Each **per-idea dossier** contains:

- **Stages** — for each stage: pass/fail, gate score, the gate's reasoning and
  `missing` list, and the stage's structured output. Failed retries are shown as
  separate attempts.
- **Full agent trace** — every isolated subagent/gate call in order (definer,
  pressure-tester, the three parallel market analysts, synthesis, discovery,
  outreach, solution, and each gate), with the exact prompt that role received
  and its structured output. Nothing is hidden behind a summary.

Use `--output DIR` to change the location, or `--no-save` to skip writing.

### Useful flags

| flag                   | default          | meaning                                            |
| ---------------------- | ---------------- | -------------------------------------------------- |
| `--mock`               | off              | Swap the SDK for deterministic stubs (offline).    |
| `--stage-model`        | `claude-opus-4-8`| Strong model for the 5 stages.                     |
| `--gate-model`         | `claude-sonnet-4-6` | Fast/cheap model for the adversarial gates. |
| `--threshold`          | `60`             | Minimum gate score (0–100) to proceed.             |
| `--retries`            | `0`              | Evaluator-optimizer retries `k` before elimination (feeds the gate's `missing` list back into the stage). `0` = drop on first fail. |
| `--concurrency`        | `4`              | Ideas processed in parallel.                       |
| `--output`             | `runs`           | Where to write per-idea records + overall report.  |
| `--no-save`            | off              | Skip writing artifacts to disk.                    |
| `--run-stage4`         | off              | Enable **live** outreach (see caveat below).       |
| `--auto-approve-sends` | off              | **DANGER:** skip human approval for sends.         |

## The stages

1. **Problem hypothesis** — two sequential subagents: a *definer* sharpens the raw
   idea into one testable hypothesis (who / how often / how severe / current
   workaround); a *pressure-tester* receives only the hypothesis and tries to
   refute it. Gate: specific **and** survived the attack.
2. **Market & competition** — three independent subagents run in parallel
   (`asyncio.gather`): competitor tiering, TAM/SAM/SOM sizing, trend analysis; a
   synthesis step merges them. Gate: real signal **and** a defensible angle.
3. **Customer discovery** — target profiles, reachable channels, and per-persona
   interview frameworks (past-focused, non-leading). Gate: right people **and**
   non-leading questions.
4. **Outreach & scheduling** — prospect list, personalized outreach, scheduling,
   tracking sheet. **Async + skippable** — see caveat. Gate: genuine signal.
5. **Solution concept** — designs the concept around what discovery *actually*
   revealed and names its 3 load-bearing assumptions + failure modes. Reaching
   and passing this = **winner**.

## ⚠️ Stage 4: human approval + async caveat

Stage 4 sends real emails and creates real calendar invites via **MCP (Gmail +
Google Calendar)** — these actions are **irreversible**. Two consequences are
baked in:

1. **Every send is gated behind explicit human approval** using the SDK's
   `can_use_tool` permission hook (`permissions.py`). Read-only/drafting tools
   pass automatically; anything that sends/creates/deletes prompts a human and is
   denied if not approved. `--auto-approve-sends` removes that guard — don't use
   it unless you mean it.
2. **It is a pause/resume boundary, not a synchronous call.** Real outreach waits
   on humans replying and interviews actually happening (days, not seconds). So
   stage 4 is **OFF by default** and runs as a synthesized placeholder (it flags
   the downstream solution as provisional) so the rest of the pipeline runs
   end-to-end. Turn on the live path with `--run-stage4`, and treat it as a
   long-lived/resumable job; the MCP server commands in `stages.py::_mcp_config`
   are placeholders to point at your own Gmail/Calendar MCP setup.

In `--mock` mode stage 4 is always synthesized — no MCP, no sends.

## Skills

Custom methods live as `SKILL.md` files under `.claude/skills/` and are scoped
**per subagent** via `AgentDefinition.skills` + the session-level `skills` filter,
so the wrong skill can't leak into the wrong stage:

| skill                 | used by                | purpose                                  |
| --------------------- | ---------------------- | ---------------------------------------- |
| `hypothesis-sharpening` | stage 1 definer      | force a testable problem statement       |
| `devils-advocate`     | stage 1 pressure-tester| structured refutation                    |
| `competitive-tiering` | stage 2 competitors    | tier + steelman the threat               |
| `tam-sam-som`         | stage 2 sizing         | bottom-up model + **deterministic xlsx builder script** |
| `interview-design`    | stage 3 discovery      | non-leading, past-focused questions      |
| `gate-rubric`         | every gate             | per-stage exit criteria as scoring rubrics |

Skills load from the **filesystem only** (the SDK can't register them
programmatically), so the runner sets `setting_sources=["user","project"]` and
points `cwd` at the project root. The pre-built **`xlsx`** skill is enabled for
the sizing and outreach roles for artifact generation (swap in `docx`/`pptx`/`pdf`
the same way).

## Test

```bash
pytest                       # runs the offline smoke test
# or, without pytest:
python tests/test_smoke.py
```

The smoke test runs the gauntlet in `--mock` mode and asserts at least one winner
and at least one elimination.

## Layout

```
src/idea_gauntlet/
  models.py       typed handoffs + GateVerdict
  config.py       models, threshold, retries, mock, stage-4 flags
  runner.py       run_agent(...) — the one SDK primitive (subagent + structured output) + mock branch
  agents.py       AgentDefinition spec per role, skills scoped per stage
  gates.py        adversarial gate (loads gate-rubric, fast model)
  stages.py       the 5 stage functions (sequential + asyncio.gather)
  permissions.py  can_use_tool human-approval hook for stage-4 sends
  trace.py        per-idea recorder (captures every subagent/gate call via contextvars)
  conductor.py    Eliminated, retry, parallelism, ranking, full per-idea record
  persist.py      writes per-idea dossiers + the overall report
  cli.py          entrypoint
.claude/skills/   the six custom skills (SKILL.md + tam-sam-som builder)
tests/            offline smoke test
```
