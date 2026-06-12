"""Orchestration — one stage at a time, user-driven.

There is no automatic run-to-completion and no elimination. The caller (API or CLI)
holds the chain of typed outputs and asks the conductor to run the next stage when
the founder chooses to continue. ``run_stage`` executes the stage, then the Coach,
and returns both plus token usage. Plain deterministic Python — no model in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from . import stages
from .coach import review_stage
from .config import EngineConfig, Usage
from .pricing import cost_usd
from .models import (
    DiscoveryPlan,
    Hypothesis,
    MarketAssessment,
    OutreachResults,
    PressureTestResult,
    SolutionConcept,
    StageReview,
)

# The typed output each stage produces — used to rebuild the previous stage's
# object from persisted JSON when resuming a run.
STAGE_OUTPUT_MODEL: dict[str, type] = {
    "hypothesis": Hypothesis,
    "pressure_test": PressureTestResult,
    "market": MarketAssessment,
    "discovery": DiscoveryPlan,
    "outreach": OutreachResults,
    "solution": SolutionConcept,
}

# Stages the generic auto-advance must NOT run — they're driven by their own
# interactive endpoints (the pressure-test interview), which write the stage result.
INTERACTIVE_STAGES: frozenset[str] = frozenset({"pressure_test"})


def rebuild_output(stage_key: str, data: dict):
    """Reconstruct a stage's typed output from its stored JSON dict."""
    return STAGE_OUTPUT_MODEL[stage_key].model_validate(data)

# The fixed order of the journey.
STAGE_ORDER: tuple[str, ...] = (
    "hypothesis", "pressure_test", "market", "discovery", "outreach", "solution"
)

STAGE_TITLES: dict[str, str] = {
    "hypothesis": "Problem hypothesis",
    "pressure_test": "Pressure test",
    "market": "Market & competition",
    "discovery": "Customer discovery",
    "outreach": "Outreach & scheduling",
    "solution": "Solution concept",
}


@dataclass(slots=True)
class StageResult:
    stage_key: str
    output: BaseModel
    review: StageReview
    usage: Usage
    cost_usd: float = 0.0

    def usage_dict(self) -> dict:
        """Token counts plus the computed dollar cost, persisted together so the API
        can roll a run's spend up without re-pricing."""
        d = self.usage.to_dict()
        d["cost_usd"] = self.cost_usd
        return d

    def to_dict(self) -> dict:
        return {
            "stage_key": self.stage_key,
            "title": STAGE_TITLES[self.stage_key],
            "output": self.output.model_dump(mode="json"),
            "review": self.review.model_dump(mode="json"),
            "usage": self.usage_dict(),
        }


def first_stage() -> str:
    return STAGE_ORDER[0]


def next_stage(stage_key: str) -> str | None:
    i = STAGE_ORDER.index(stage_key)
    return STAGE_ORDER[i + 1] if i + 1 < len(STAGE_ORDER) else None


async def run_stage(
    stage_key: str,
    prior: object,
    config: EngineConfig,
    *,
    scheduling_link: str = "",
    contacts_text: str = "",
    edits: str = "",
) -> StageResult:
    """Run one stage given the previous stage's output (or the idea string for the
    first stage), then run the Coach over the stage output."""
    if stage_key == "hypothesis":
        output, usage = await stages.stage_hypothesis(str(prior), config, edits=edits)
    elif stage_key == "market":
        output, usage = await stages.stage_market(prior, config)  # type: ignore[arg-type]
    elif stage_key == "discovery":
        output, usage = await stages.stage_discovery(prior, config)  # type: ignore[arg-type]
    elif stage_key == "outreach":
        output, usage = await stages.stage_outreach(
            prior,  # type: ignore[arg-type]
            config,
            scheduling_link=scheduling_link,
            contacts_text=contacts_text,
        )
    elif stage_key == "solution":
        output, usage = await stages.stage_solution(prior, config)  # type: ignore[arg-type]
    else:
        raise ValueError(f"Unknown stage: {stage_key!r}")

    review, review_usage = await review_stage(stage_key, output, config)
    # Price each model's tokens at its own rate before merging the buckets: the stage
    # sub-roles run on the stage model, the Coach on the (cheaper) coach model.
    cost = cost_usd(config.stage_model, usage) + cost_usd(config.coach_model, review_usage)
    usage.add(review_usage)
    return StageResult(
        stage_key=stage_key, output=output, review=review, usage=usage, cost_usd=cost
    )
