"""The five stages.

Each stage is a plain async function taking the previous stage's typed object and
returning the next typed object plus token usage. Within a stage, sub-roles run as
isolated calls — sequentially (stage 1) or concurrently (stage 2). Stages contain
no Coach logic; the conductor pairs each stage with a Coach review.

Each stage receives ONLY the previous stage's structured output (JSON). The models
carry forward the upstream essentials downstream stages need, so output-only
handoffs hold without smuggling in upstream reasoning.
"""

from __future__ import annotations

import asyncio

from . import roles
from .client import run_agent
from .config import EngineConfig, Usage
from .models import (
    CompetitorLandscape,
    DiscoveryPlan,
    Hypothesis,
    MarketAssessment,
    MarketSizing,
    MarketVerdict,
    OutreachResults,
    PressureTestResult,
    SolutionConcept,
    TrendAnalysis,
)


# --------------------------------------------------------------------------- #
# Stage 1 — Problem hypothesis (two sequential sub-roles)
# --------------------------------------------------------------------------- #
async def stage_hypothesis(
    idea: str, config: EngineConfig, *, edits: str = ""
) -> tuple[Hypothesis, Usage]:
    """Generate ONE sharp, testable, cited problem hypothesis. `edits` lets the
    founder regenerate with their own guidance."""
    guidance = ""
    if edits:
        guidance = (
            "\n\nThe founder reviewed a previous version and asked for these changes — "
            f"honour them:\n{edits}"
        )
    hyp, _, usage = await run_agent(
        role=roles.HYPOTHESIS_BUILDER,
        prompt=(
            f"Raw idea:\n{idea}{guidance}\n\nProduce one sharp, testable problem "
            "hypothesis with cited evidence and its key assumptions."
        ),
        schema=Hypothesis,
        config=config,
    )
    return hyp, usage


# --------------------------------------------------------------------------- #
# Stage 2 — Market & competition (3 independent sub-roles in parallel + synthesis)
# --------------------------------------------------------------------------- #
async def stage_market(
    pt: PressureTestResult, config: EngineConfig
) -> tuple[MarketAssessment, Usage]:
    usage = Usage.zero()
    hyp_json = pt.hypothesis.model_dump_json(indent=2)
    base = (
        f"Validated hypothesis (post pressure-test):\n{hyp_json}\n\n"
        f"Pressure-test verdict: survived={pt.survived}. {pt.attack_summary}"
    )

    (competitors, cs, u1), (sizing, ss, u2), (trends, ts, u3) = await asyncio.gather(
        run_agent(role=roles.COMPETITOR_TIERING, prompt=base, schema=CompetitorLandscape, config=config),
        run_agent(role=roles.TAM_SIZING, prompt=base, schema=MarketSizing, config=config),
        run_agent(role=roles.TREND_ANALYSIS, prompt=base, schema=TrendAnalysis, config=config),
    )
    for u in (u1, u2, u3):
        usage.add(u)

    # Backfill a sub-analysis's top-level sources from what it actually consulted, so a
    # figure/threat always shows provenance even if the model forgot to attach it.
    if not competitors.sources:
        competitors.sources = cs[:4]
    if not sizing.sources:
        sizing.sources = ss[:4]

    # The synthesis produces ONLY the verdict; we assemble the assessment in code so the
    # cited competitors/sizing/trends are preserved verbatim (the model can't drop them).
    verdict, vs, u = await run_agent(
        role=roles.MARKET_SYNTHESIS,
        prompt=(
            "Give the market verdict for this hypothesis based ONLY on the three cited "
            f"analyses below.\n\nHYPOTHESIS:\n{hyp_json}\n\n"
            f"COMPETITORS:\n{competitors.model_dump_json(indent=2)}\n\n"
            f"SIZING:\n{sizing.model_dump_json(indent=2)}\n\n"
            f"TRENDS:\n{trends.model_dump_json(indent=2)}"
        ),
        schema=MarketVerdict,
        config=config,
    )
    usage.add(u)

    merged = MarketAssessment(
        hypothesis_recap=verdict.hypothesis_recap,
        competitors=competitors,
        sizing=sizing,
        trends=trends,
        real_signal=verdict.real_signal,
        defensible_angle=verdict.defensible_angle,
        sources=verdict.sources or vs[:4],
    )
    return merged, usage


# --------------------------------------------------------------------------- #
# Stage 3 — Customer discovery
# --------------------------------------------------------------------------- #
async def stage_discovery(
    market: MarketAssessment, config: EngineConfig
) -> tuple[DiscoveryPlan, Usage]:
    plan, _, usage = await run_agent(
        role=roles.DISCOVERY_DESIGNER,
        prompt=(
            "Design customer discovery from this market assessment. Carry the "
            f"hypothesis forward as hypothesis_recap.\n\n{market.model_dump_json(indent=2)}"
        ),
        schema=DiscoveryPlan,
        config=config,
    )
    return plan, usage


# --------------------------------------------------------------------------- #
# Stage 4 — Outreach (drafts + scheduling link; no auto-send)
# --------------------------------------------------------------------------- #
async def stage_outreach(
    plan: DiscoveryPlan,
    config: EngineConfig,
    *,
    scheduling_link: str = "",
    contacts_text: str = "",
) -> tuple[OutreachResults, Usage]:
    extra = ""
    if scheduling_link:
        extra += f"\n\nFounder's scheduling link (paste verbatim into each draft):\n{scheduling_link}"
    if contacts_text:
        extra += (
            "\n\nCandidate contacts (match these to the target profile; use real "
            f"names/companies where given):\n{contacts_text}"
        )
    out, _, usage = await run_agent(
        role=roles.OUTREACH,
        prompt=(
            "Prepare outreach the founder will send themselves: a prospect list with "
            "a personalized draft email each, plus a copyable interview guide. Report "
            "interviews_completed=0 and keep discovery_findings honest (provisional "
            f"until real interviews happen).\n\n{plan.model_dump_json(indent=2)}{extra}"
        ),
        schema=OutreachResults,
        config=config,
    )
    return out, usage


# --------------------------------------------------------------------------- #
# Stage 5 — Solution concept
# --------------------------------------------------------------------------- #
async def stage_solution(
    outreach: OutreachResults, config: EngineConfig
) -> tuple[SolutionConcept, Usage]:
    concept, _, usage = await run_agent(
        role=roles.SOLUTION_CONCEPT,
        prompt=(
            "Design the solution concept grounded in what discovery ACTUALLY revealed "
            "below — not the original assumption. Name the 3 load-bearing "
            f"assumptions.\n\n{outreach.model_dump_json(indent=2)}"
        ),
        schema=SolutionConcept,
        config=config,
    )
    return concept, usage
