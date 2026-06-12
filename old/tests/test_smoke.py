"""End-to-end smoke test in --mock mode: zero API calls, fully deterministic.

Asserts the gauntlet produces at least one WINNER and at least one ELIMINATION,
exercising stages, gates, elimination, ranking, and parallelism offline.
"""

from __future__ import annotations

import asyncio

from idea_gauntlet.config import GauntletConfig
from idea_gauntlet.conductor import run_gauntlet

# One clean idea (should win) and one carrying a WEAK_MARKER (should be eliminated
# at the first gate by the deterministic mock judge).
IDEAS = [
    "AI expense reconciliation for mid-market finance teams",
    "A social network for cats — the market is saturated and nobody wants it",
    "Version-controlled contract redlining for in-house legal teams",
]


def _run() -> list:
    config = GauntletConfig(mock=True, retry_k=0, max_concurrency=3)
    return asyncio.run(run_gauntlet(IDEAS, config))


def test_gauntlet_has_winner_and_elimination():
    results = _run()
    winners = [r for r in results if r.won]
    eliminated = [r for r in results if not r.won]

    assert len(winners) >= 1, "expected at least one winner"
    assert len(eliminated) >= 1, "expected at least one elimination"

    # The weak-marker idea must be the one eliminated, and at the hypothesis gate.
    weak = next(r for r in results if "saturated" in r.idea)
    assert not weak.won
    assert weak.eliminated_stage == "hypothesis"

    # Winners must carry a positive accumulated score and a final SolutionConcept.
    for w in winners:
        assert w.total_score > 0
        assert w.final_output is not None


def test_ranking_is_descending_for_winners():
    results = _run()
    winners = [r for r in results if r.won]
    scores = [w.total_score for w in winners]
    assert scores == sorted(scores, reverse=True)


if __name__ == "__main__":
    # Allow `python tests/test_smoke.py` without pytest installed.
    test_gauntlet_has_winner_and_elimination()
    test_ranking_is_descending_for_winners()
    print("smoke test passed: winner(s) and elimination(s) produced offline.")
