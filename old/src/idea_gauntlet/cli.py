"""CLI entrypoint: feed in ideas, run the gauntlet, print outcomes + ranking.

    python -m idea_gauntlet --mock --ideas ideas.txt
    python -m idea_gauntlet "AI expense reconciliation for mid-market finance teams"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .conductor import IdeaResult, run_gauntlet
from .config import DEFAULT_GATE_MODEL, DEFAULT_STAGE_MODEL, GauntletConfig
from .persist import persist_run


def _load_ideas(args: argparse.Namespace) -> list[str]:
    ideas: list[str] = list(args.ideas_pos)
    if args.ideas:
        path = Path(args.ideas)
        if not path.exists():
            sys.exit(f"ideas file not found: {path}")
        ideas += [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not ideas:
        sys.exit("No ideas provided. Pass them as args or via --ideas FILE.")
    return ideas


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="idea_gauntlet",
        description="Gated multi-agent gauntlet for validating startup ideas.",
    )
    p.add_argument("ideas_pos", nargs="*", metavar="IDEA", help="Ideas as positional args.")
    p.add_argument("--ideas", metavar="FILE", help="Text file with one idea per line.")
    p.add_argument("--mock", action="store_true", help="Run offline with deterministic stubs.")
    p.add_argument("--stage-model", default=DEFAULT_STAGE_MODEL, help="Strong model for stages.")
    p.add_argument("--gate-model", default=DEFAULT_GATE_MODEL, help="Fast model for gates.")
    p.add_argument("--threshold", type=int, default=60, help="Min gate score to proceed (0-100).")
    p.add_argument("--retries", type=int, default=0, dest="retry_k",
                   help="Evaluator-optimizer retries per gate before elimination (k).")
    p.add_argument("--concurrency", type=int, default=4, help="Ideas processed in parallel.")
    p.add_argument("--output", metavar="DIR", default="runs",
                   help="Where to write per-idea records + the overall report (default: runs/).")
    p.add_argument("--no-save", action="store_true", help="Skip writing artifacts to disk.")
    p.add_argument("--run-stage4", action="store_true",
                   help="Enable live outreach (MCP + human-approved sends). Off by default.")
    p.add_argument("--auto-approve-sends", action="store_true",
                   help="DANGER: skip human approval for irreversible sends.")
    return p.parse_args(argv)


def _print_report(results: list[IdeaResult]) -> None:
    winners = [r for r in results if r.won]
    eliminated = [r for r in results if not r.won]

    print("\n" + "=" * 72)
    print("PER-IDEA OUTCOMES")
    print("=" * 72)
    for r in results:
        print(f"\n• {r.idea}")
        print(f"    {r.outcome}")
        if r.gate_scores:
            scores = ", ".join(f"{k}={v}" for k, v in r.gate_scores.items())
            print(f"    gate scores: {scores}")

    print("\n" + "=" * 72)
    print(f"RANKED WINNERS ({len(winners)} of {len(results)})")
    print("=" * 72)
    if not winners:
        print("  (none reached problem-solution fit)")
    for rank, r in enumerate(winners, 1):
        print(f"  {rank}. [{r.total_score:>4}] {r.idea}")

    print(f"\nEliminated: {len(eliminated)}")
    for r in eliminated:
        print(f"  - ({r.eliminated_stage}) {r.idea}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ideas = _load_ideas(args)

    config = GauntletConfig(
        stage_model=args.stage_model,
        gate_model=args.gate_model,
        gate_threshold=args.threshold,
        retry_k=args.retry_k,
        mock=args.mock,
        max_concurrency=args.concurrency,
        run_stage4=args.run_stage4,
        auto_approve_sends=args.auto_approve_sends,
    )

    if not config.mock and not config.api_key:
        sys.exit("ANTHROPIC_API_KEY is not set. Export it, or run with --mock.")

    print(f"Running {len(ideas)} idea(s) | mock={config.mock} | "
          f"stage={config.stage_model} gate={config.gate_model} | "
          f"threshold={config.gate_threshold} retries={config.retry_k}")

    results = asyncio.run(run_gauntlet(ideas, config))
    _print_report(results)

    if not args.no_save:
        run_dir = persist_run(args.output, results, config)
        print(f"\nFull records written to: {run_dir}")
        print(f"  overall report : {run_dir / 'report.md'}")
        print(f"  per-idea dossiers: {run_dir / 'ideas'}/<slug>/report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
