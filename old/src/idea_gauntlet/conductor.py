"""The conductor: plain deterministic Python, no LLM in the orchestration loop.

It runs M ideas concurrently, pushes each through the 5 stages, applies an
adversarial gate after every stage, eliminates losers (recording which gate
killed them and why), optionally retries a failed stage by feeding the gate's
`missing` list back in, collects survivors, and ranks winners by summed gate
score.

It also records EVERYTHING per idea: each stage's handoff output, every gate
verdict (incl. failed retry attempts), and — via the trace recorder — every
underlying subagent call (definer, pressure-tester, the three market analysts,
synthesis, etc.). `IdeaResult.to_dict()` serializes the whole thing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .config import GauntletConfig
from .gates import evaluate_gate
from .models import GateVerdict
from .stages import (
    stage_discovery,
    stage_hypothesis,
    stage_market,
    stage_outreach,
    stage_solution,
)
from .trace import IdeaRecorder, set_recorder

# The pipeline: (stage_key, stage_fn). The gate for each stage uses the same key.
PIPELINE = [
    ("hypothesis", stage_hypothesis),
    ("market", stage_market),
    ("discovery", stage_discovery),
    ("outreach", stage_outreach),
    ("solution", stage_solution),
]


@dataclass(slots=True)
class GateAttempt:
    """One stage run + its gate verdict (there can be several, due to retries)."""

    attempt: int
    stage_output: dict[str, Any]   # the stage handoff object, as JSON-able dict
    verdict: dict[str, Any]        # GateVerdict, as JSON-able dict


@dataclass(slots=True)
class StageRecord:
    stage_key: str
    passed: bool
    score: int
    attempts: list[GateAttempt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage_key,
            "passed": self.passed,
            "score": self.score,
            "attempts": [
                {"attempt": a.attempt, "output": a.stage_output, "verdict": a.verdict}
                for a in self.attempts
            ],
        }


class Eliminated(Exception):
    """Raised when an idea fails a gate (after exhausting retries)."""

    def __init__(self, stage_key: str, verdict: GateVerdict, attempts: list[GateAttempt]):
        self.stage_key = stage_key
        self.verdict = verdict
        self.attempts = attempts
        super().__init__(f"eliminated at '{stage_key}': {verdict.reasoning}")


@dataclass(slots=True)
class IdeaResult:
    idea: str
    won: bool
    total_score: int = 0
    eliminated_stage: str | None = None
    eliminated_reason: str | None = None
    gate_scores: dict[str, int] = field(default_factory=dict)
    stages: list[StageRecord] = field(default_factory=list)
    final_output: BaseModel | None = None       # SolutionConcept for winners
    recorder: IdeaRecorder | None = None         # full granular agent-call trace

    @property
    def outcome(self) -> str:
        if self.won:
            return f"WINNER (score {self.total_score})"
        return (
            f"eliminated at stage '{self.eliminated_stage}' "
            f"because: {self.eliminated_reason}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Everything we know about this idea — the persisted record."""
        return {
            "idea": self.idea,
            "won": self.won,
            "outcome": self.outcome,
            "total_score": self.total_score,
            "gate_scores": self.gate_scores,
            "eliminated_stage": self.eliminated_stage,
            "eliminated_reason": self.eliminated_reason,
            "stages": [s.to_dict() for s in self.stages],
            "final_output": (
                self.final_output.model_dump(mode="json") if self.final_output else None
            ),
            "trace": [
                {
                    "seq": c.seq,
                    "role": c.role,
                    "is_gate": c.is_gate,
                    "prompt": c.prompt,
                    "output": c.output,
                }
                for c in (self.recorder.calls if self.recorder else [])
            ],
        }


async def _run_stage(
    stage_key: str, stage_fn, stage_input, config: GauntletConfig
) -> tuple[BaseModel, GateVerdict, list[GateAttempt]]:
    """Run one stage, then its gate, retrying up to `retry_k` times by feeding the
    gate's `missing` list back into the stage. Returns (output, verdict, attempts)
    on success; raises Eliminated (carrying the attempts) on final failure."""
    attempts: list[GateAttempt] = []
    feedback: list[str] | None = None
    last_verdict: GateVerdict | None = None

    for i in range(config.retry_k + 1):
        output = await stage_fn(stage_input, config, feedback)
        verdict = await evaluate_gate(stage_key, output, config)
        last_verdict = verdict
        attempts.append(
            GateAttempt(
                attempt=i + 1,
                stage_output=output.model_dump(mode="json"),
                verdict=verdict.model_dump(mode="json"),
            )
        )
        if verdict.proceed and verdict.score >= config.gate_threshold:
            return output, verdict, attempts
        feedback = verdict.missing or ["address the gate's reasoning above"]

    assert last_verdict is not None
    raise Eliminated(stage_key, last_verdict, attempts)


async def run_idea(idea: str, config: GauntletConfig) -> IdeaResult:
    """Push a single idea through the gauntlet, recording every step."""
    recorder = IdeaRecorder(idea=idea)
    set_recorder(recorder)  # bound to THIS idea's async context (see trace.py)

    result = IdeaResult(idea=idea, won=False, recorder=recorder)
    prev_output: BaseModel | None = None

    try:
        for stage_key, stage_fn in PIPELINE:
            # First stage takes the raw idea; the rest take the upstream object.
            stage_input = idea if stage_key == "hypothesis" else prev_output
            output, verdict, attempts = await _run_stage(
                stage_key, stage_fn, stage_input, config
            )
            result.stages.append(StageRecord(stage_key, True, verdict.score, attempts))
            result.gate_scores[stage_key] = verdict.score
            result.total_score += verdict.score
            prev_output = output

        result.won = True
        result.final_output = prev_output
    except Eliminated as e:
        result.stages.append(
            StageRecord(e.stage_key, False, e.verdict.score, e.attempts)
        )
        result.eliminated_stage = e.stage_key
        result.eliminated_reason = e.verdict.reasoning
        result.total_score = sum(result.gate_scores.values())

    return result


async def run_gauntlet(ideas: list[str], config: GauntletConfig) -> list[IdeaResult]:
    """Run all ideas concurrently (bounded) and return results ranked: winners
    first by descending score, then eliminations."""
    sem = asyncio.Semaphore(config.max_concurrency)

    async def _bounded(idea: str) -> IdeaResult:
        async with sem:
            return await run_idea(idea, config)

    results = await asyncio.gather(*(_bounded(i) for i in ideas))

    # Rank: winners by summed gate score (desc); eliminations after, by score.
    results.sort(key=lambda r: (r.won, r.total_score), reverse=True)
    return list(results)
