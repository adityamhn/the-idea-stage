"""The pressure test — a multi-turn devil's-advocate interview.

A sharp VC opens with the strongest, cited case against the hypothesis, then
interviews the founder turn-by-turn, drilling into weak answers. When the founder
(or the interviewer) is done, ``conclude`` synthesizes a structured, cited verdict.

The interview turns use the free-text ``run_chat`` primitive; the conclusion uses
structured ``run_agent``. The caller (API store) owns persistence of the transcript.
Visible messages are passed in as ``[{"role": "assistant"|"user", "text": str}, ...]``.
"""

from __future__ import annotations

from . import roles
from .client import run_agent, run_chat
from .config import EngineConfig, Usage
from .models import Citation, Hypothesis, PressureTestResult, PressureTestSynthesis


def _seed(hyp: Hypothesis) -> dict:
    return {
        "role": "user",
        "content": (
            "Hypothesis to pressure-test:\n"
            f"{hyp.model_dump_json(indent=2)}\n\n"
            "Open the pressure test now: state the strongest case against it (grounded "
            "in current evidence, with real source URLs) and ask your first question."
        ),
    }


def _convo(hyp: Hypothesis, visible: list[dict]) -> list[dict]:
    msgs = [_seed(hyp)]
    for m in visible:
        msgs.append({"role": m["role"], "content": m["text"]})
    return msgs


def _cited_only(text: str, sources: list[Citation]) -> list[Citation]:
    """Keep only sources the interviewer actually cited inline (their URL appears in the
    message). Web search returns every page it looked at; surfacing all of them buries
    the real evidence under decorative links."""
    return [s for s in sources if s.url and s.url in text]


async def open_interview(
    hyp: Hypothesis, config: EngineConfig
) -> tuple[str, list[Citation], Usage]:
    text, sources, usage = await run_chat(
        role=roles.INTERVIEWER, messages=_convo(hyp, []), config=config, web_search=True
    )
    return text, _cited_only(text, sources), usage


async def next_reply(
    hyp: Hypothesis, visible: list[dict], founder_text: str, config: EngineConfig
) -> tuple[str, list[Citation], Usage]:
    convo = _convo(hyp, visible) + [{"role": "user", "content": founder_text}]
    text, sources, usage = await run_chat(
        role=roles.INTERVIEWER, messages=convo, config=config, web_search=True
    )
    return text, _cited_only(text, sources), usage


async def conclude(
    hyp: Hypothesis, visible: list[dict], config: EngineConfig
) -> tuple[PressureTestResult, list[Citation], Usage]:
    transcript = "\n\n".join(f"{m['role'].upper()}: {m['text']}" for m in visible)
    synth, sources, usage = await run_agent(
        role=roles.PRESSURE_SYNTHESIS,
        prompt=(
            f"HYPOTHESIS:\n{hyp.model_dump_json(indent=2)}\n\n"
            f"INTERVIEW TRANSCRIPT:\n{transcript or '(no founder answers given)'}\n\n"
            "Synthesize the pressure-test verdict."
        ),
        schema=PressureTestSynthesis,
        config=config,
    )
    result = PressureTestResult(**synth.model_dump(), hypothesis=hyp)
    return result, sources, usage
