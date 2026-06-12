"""Write the run to disk: a full record per idea + one overall report.

Layout (under a timestamped run directory so runs never clobber each other):

    <output>/run-YYYYMMDD-HHMMSS/
        report.md            human-readable overall report (scores + descriptions)
        report.json          machine-readable: every idea's full to_dict()
        ideas/<slug>/
            idea.json        the complete per-idea record (stages + full trace)
            report.md        human-readable per-idea dossier

The per-idea dossier surfaces the hypothesis, the research, the pressure test,
each gate's score + reasoning, and exactly why a failed idea died — plus a full
chronological trace of every subagent call.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import GauntletConfig
from .conductor import IdeaResult

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, maxlen: int = 60) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return (s[:maxlen].rstrip("-")) or "idea"


def _json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _fence(obj: Any) -> str:
    """A fenced JSON block for embedding a dict/list in markdown."""
    return f"```json\n{_json(obj)}\n```"


# --------------------------------------------------------------------------- #
# Per-idea markdown dossier
# --------------------------------------------------------------------------- #
def _idea_markdown(result: IdeaResult) -> str:
    d = result.to_dict()
    lines: list[str] = []
    lines.append(f"# {result.idea}\n")
    lines.append(f"**Outcome:** {d['outcome']}  ")
    lines.append(f"**Total score:** {d['total_score']}  ")
    if d["gate_scores"]:
        pairs = ", ".join(f"{k}={v}" for k, v in d["gate_scores"].items())
        lines.append(f"**Gate scores:** {pairs}  ")
    if not result.won:
        lines.append(
            f"**Eliminated at:** `{d['eliminated_stage']}` — {d['eliminated_reason']}  "
        )
    lines.append("")

    # Per-stage section: outputs + gate verdicts (including failed retries).
    lines.append("## Stages\n")
    for s in d["stages"]:
        status = "✅ passed" if s["passed"] else "❌ failed"
        lines.append(f"### Stage: `{s['stage']}` — {status} (score {s['score']})\n")
        for att in s["attempts"]:
            v = att["verdict"]
            if len(s["attempts"]) > 1:
                lines.append(f"#### Attempt {att['attempt']}\n")
            lines.append(
                f"- **Gate verdict:** proceed={v['proceed']}, score={v['score']}"
            )
            if v.get("missing"):
                lines.append(f"- **Missing:** {', '.join(v['missing'])}")
            lines.append(f"- **Gate reasoning:** {v['reasoning']}\n")
            lines.append("**Stage output:**\n")
            lines.append(_fence(att["output"]))
            lines.append("")

    # Full chronological trace of every underlying subagent/gate call.
    lines.append("## Full agent trace\n")
    lines.append(
        "_Every isolated subagent call in order — definer, pressure-tester, the "
        "parallel market analysts, synthesis, discovery, outreach, solution, and "
        "each gate. `prompt` is exactly what that role received._\n"
    )
    for c in d["trace"]:
        kind = "GATE" if c["is_gate"] else "stage"
        lines.append(f"### {c['seq']}. `{c['role']}` ({kind})\n")
        lines.append("<details><summary>Prompt (input the role saw)</summary>\n")
        lines.append(f"```\n{c['prompt']}\n```")
        lines.append("</details>\n")
        lines.append("**Output:**\n")
        lines.append(_fence(c["output"]))
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Overall report markdown
# --------------------------------------------------------------------------- #
def _overall_markdown(results: list[IdeaResult], config: GauntletConfig, when: str) -> str:
    winners = [r for r in results if r.won]
    eliminated = [r for r in results if not r.won]

    lines: list[str] = []
    lines.append("# Idea Gauntlet — Run Report\n")
    lines.append(f"- **When:** {when}")
    lines.append(f"- **Ideas:** {len(results)}  |  **Winners:** {len(winners)}  "
                 f"|  **Eliminated:** {len(eliminated)}")
    lines.append(f"- **Mock:** {config.mock}  |  **Stage model:** `{config.stage_model}`  "
                 f"|  **Gate model:** `{config.gate_model}`")
    lines.append(f"- **Threshold:** {config.gate_threshold}  |  **Retries (k):** {config.retry_k}\n")

    # Summary table.
    lines.append("## Summary\n")
    lines.append("| Rank | Score | Outcome | Idea |")
    lines.append("| ---: | ---: | --- | --- |")
    for i, r in enumerate(results, 1):
        outcome = "WINNER" if r.won else f"eliminated @ {r.eliminated_stage}"
        idea_short = (r.idea[:80] + "…") if len(r.idea) > 81 else r.idea
        lines.append(f"| {i} | {r.total_score} | {outcome} | {idea_short} |")
    lines.append("")

    # Ranked winners with per-stage scores.
    lines.append("## Ranked winners\n")
    if not winners:
        lines.append("_None reached problem-solution fit._\n")
    for rank, r in enumerate(winners, 1):
        slug = _slug(r.idea)
        pairs = ", ".join(f"{k}={v}" for k, v in r.gate_scores.items())
        lines.append(f"{rank}. **[{r.total_score}]** {r.idea}")
        lines.append(f"   - gate scores: {pairs}")
        lines.append(f"   - dossier: `ideas/{slug}/report.md`")
    lines.append("")

    # Eliminations with the killing reason.
    lines.append("## Eliminations\n")
    if not eliminated:
        lines.append("_None._\n")
    for r in eliminated:
        slug = _slug(r.idea)
        lines.append(f"- **{r.idea}**")
        lines.append(f"  - died at `{r.eliminated_stage}` (score {r.total_score}): "
                     f"{r.eliminated_reason}")
        lines.append(f"  - dossier: `ideas/{slug}/report.md`")
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def persist_run(base_dir: str | Path, results: list[IdeaResult],
                config: GauntletConfig) -> Path:
    """Write all artifacts and return the run directory."""
    when = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(base_dir) / f"run-{when}"
    ideas_dir = run_dir / "ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)

    # Per-idea artifacts. Disambiguate slug collisions with an index suffix.
    seen: dict[str, int] = {}
    for r in results:
        slug = _slug(r.idea)
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        d = ideas_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "idea.json").write_text(_json(r.to_dict()), encoding="utf-8")
        (d / "report.md").write_text(_idea_markdown(r), encoding="utf-8")

    # Overall report.
    (run_dir / "report.json").write_text(
        _json({
            "generated_at": when,
            "config": {
                "mock": config.mock,
                "stage_model": config.stage_model,
                "gate_model": config.gate_model,
                "gate_threshold": config.gate_threshold,
                "retry_k": config.retry_k,
            },
            "ideas": [r.to_dict() for r in results],
        }),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(
        _overall_markdown(results, config, when), encoding="utf-8"
    )
    return run_dir
