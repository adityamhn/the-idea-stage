"""The adversarial gate between every stage.

A gate is a cheap LLM-as-judge on the fast model. It sees ONLY the stage's
structured output (as JSON), loads the `gate-rubric` skill, and returns a
`GateVerdict`. The conductor — not the gate — decides what happens with the
verdict (proceed, retry, or eliminate).
"""

from __future__ import annotations

from pydantic import BaseModel

from .agents import gate_role
from .config import GauntletConfig
from .models import GateVerdict
from .runner import run_agent

# Human-readable exit-criteria reminder injected into each gate prompt. The full
# rubric lives in the gate-rubric skill; this keeps the ask sharp.
EXIT_CRITERIA: dict[str, str] = {
    "hypothesis": "Specific (who/often/severe/workaround) AND survived the refutation.",
    "market": "Real market signal AND a defensible angle that rivals won't trivially copy.",
    "discovery": "Right people targeted AND interview questions are non-leading & past-focused.",
    "outreach": "Genuine interview signal gathered (or a sound mock), tracking intact.",
    "solution": "Concept addresses the REVEALED problem; 3 load-bearing assumptions named.",
}


async def evaluate_gate(
    stage_key: str,
    stage_output: BaseModel,
    config: GauntletConfig,
) -> GateVerdict:
    """Score a stage's output against its exit criteria, adversarially."""
    criteria = EXIT_CRITERIA[stage_key]
    prompt = (
        f"Exit criteria for the '{stage_key}' stage: {criteria}\n\n"
        f"Stage output to judge (JSON):\n{stage_output.model_dump_json(indent=2)}\n\n"
        "Score 0-100 how convincingly this output MEETS the criteria. Hunt for "
        "reasons to stop. If you would not bet on it, score low and list the gaps "
        "in `missing`."
    )
    verdict = await run_agent(
        spec=gate_role(stage_key),
        prompt=prompt,
        schema=GateVerdict,
        config=config,
    )
    assert isinstance(verdict, GateVerdict)
    return verdict
