"""A small CLI to step through the journey for manual verification.

    python -m engine --mock --idea "AI expense reconciliation for finance teams"
    python -m engine --mock --auto --idea "..."     # run all stages, no prompts

Live mode needs ANTHROPIC_API_KEY. This is a dev/verification tool; the product
surface is the web app.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import pressure_test
from .coach import review_stage
from .conductor import STAGE_ORDER, STAGE_TITLES, StageResult, run_stage
from .config import EngineConfig
from .pricing import cost_usd


def _print_result(result) -> None:
    print("\n" + "=" * 72)
    print(f"STAGE: {STAGE_TITLES[result.stage_key]}")
    print("=" * 72)
    print("\n--- output ---")
    print(json.dumps(result.output.model_dump(mode="json"), indent=2))
    r = result.review
    print("\n--- coach ---")
    print(f"summary:        {r.summary}")
    print(f"what this means: {r.what_this_means}")
    if r.strengths:
        print("strengths:      " + "; ".join(r.strengths))
    if r.risks:
        print("risks:          " + "; ".join(r.risks))
    for f in r.playbook_flags:
        print(f"⚑ {f.principle}: {f.note}")
    print(f"suggested next: {r.suggested_next}")
    print(f"\n(tokens: {result.usage.to_dict()})")


async def _pressure_test(hyp, config: EngineConfig, auto: bool) -> StageResult:
    """The interactive stage: interview in the terminal, then conclude + Coach.
    In --auto mode the interviewer opens and we conclude with no founder answers."""
    usage_total = None
    opening, _, usage_total = await pressure_test.open_interview(hyp, config)
    print("\n" + "=" * 72)
    print("PRESSURE TEST — a VC interviews you (empty answer concludes)")
    print("=" * 72)
    print(f"\nVC: {opening}")
    visible = [{"role": "assistant", "text": opening}]
    if not auto:
        while True:
            answer = input("\nYou: ").strip()
            if not answer:
                break
            visible.append({"role": "user", "text": answer})
            reply, _, u = await pressure_test.next_reply(hyp, visible[:-1], answer, config)
            usage_total.add(u)
            visible.append({"role": "assistant", "text": reply})
            print(f"\nVC: {reply}")

    result_out, _, u = await pressure_test.conclude(hyp, visible, config)
    usage_total.add(u)
    review, review_usage = await review_stage("pressure_test", result_out, config)
    cost = cost_usd(config.stage_model, usage_total) + cost_usd(config.coach_model, review_usage)
    usage_total.add(review_usage)
    return StageResult(
        stage_key="pressure_test", output=result_out, review=review,
        usage=usage_total, cost_usd=cost,
    )


async def _run(idea: str, config: EngineConfig, auto: bool, scheduling_link: str) -> None:
    prior: object = idea
    for stage_key in STAGE_ORDER:
        if stage_key == "pressure_test":
            result = await _pressure_test(prior, config, auto)
        else:
            result = await run_stage(stage_key, prior, config, scheduling_link=scheduling_link)
        _print_result(result)
        prior = result.output
        if stage_key == STAGE_ORDER[-1]:
            break
        if not auto:
            ans = input("\nContinue to the next stage? [Y/n] ").strip().lower()
            if ans == "n":
                print("Stopped by user.")
                return
    print("\n✓ Reached the solution concept.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="idea-stage")
    p.add_argument("idea", nargs="?", help="The idea to validate.")
    p.add_argument("--idea", dest="idea_opt", help="The idea to validate.")
    p.add_argument("--mock", action="store_true", help="Run offline with deterministic stubs.")
    p.add_argument("--auto", action="store_true", help="Run all stages without prompting.")
    p.add_argument("--scheduling-link", default="", help="Cal.com/Calendly link for stage 4.")
    args = p.parse_args(argv)

    idea = args.idea_opt or args.idea
    if not idea:
        p.error("provide an idea (positional or --idea)")

    config = EngineConfig(mock=args.mock)
    if not config.mock and not config.api_key:
        sys.exit("ANTHROPIC_API_KEY is not set. Use --mock for offline runs.")

    asyncio.run(_run(idea, config, args.auto, args.scheduling_link))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
