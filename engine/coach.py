"""The Coach — a plain-language reviewer that runs after every stage.

This replaces the old adversarial scoring gate. It produces a ``StageReview`` that
explains the stage to the founder, names concrete strengths and risks, and flags
any of the three playbook traps. It never scores and never blocks: the founder
decides whether to continue.
"""

from __future__ import annotations

from pydantic import BaseModel

from . import roles
from .client import run_agent
from .config import EngineConfig, Usage
from .models import StageReview
from .playbook import playbook_brief

# What each stage is trying to establish — given to the Coach as orientation.
_STAGE_INTENT = {
    "hypothesis": "establish a specific, real problem worth a serious look",
    "pressure_test": "stress-test the hypothesis against evidence and the founder's own answers",
    "market": "establish a real, bottom-up market signal and a defensible angle",
    "discovery": "line up the right people and non-leading, past-focused questions",
    "outreach": "prepare real outreach; keep the solution provisional until interviews happen",
    "solution": "design a concept that addresses the REVEALED problem, with honest assumptions",
}


async def review_stage(
    stage_key: str, stage_output: BaseModel, config: EngineConfig
) -> tuple[StageReview, Usage]:
    intent = _STAGE_INTENT.get(stage_key, "")
    prompt = (
        f"The founder just completed the '{stage_key}' stage, whose job is to {intent}.\n\n"
        f"Here is the playbook this product follows:\n{playbook_brief()}\n\n"
        f"Here is the stage's structured output (JSON):\n"
        f"{stage_output.model_dump_json(indent=2)}\n\n"
        "Coach the founder on this result."
    )
    review, _, usage = await run_agent(
        role=roles.coach_role(stage_key),
        prompt=prompt,
        schema=StageReview,
        config=config,
    )
    return review, usage
