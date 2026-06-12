"""The five pipeline stages.

Each stage is a plain async function: it takes the previous stage's typed object
(plus optional retry `feedback`) and returns the next typed object. Within a
stage, sub-roles run as isolated subagents — sequentially (stage 1) or in
parallel via asyncio.gather (stage 2). The conductor wires stages to gates; the
stages themselves contain no gate logic.

Each stage receives ONLY the previous stage's structured output. The models
carry forward the upstream essentials downstream stages need (e.g.
`hypothesis_recap`), so "output-only handoffs" holds without smuggling in
upstream reasoning.
"""

from __future__ import annotations

import asyncio

from . import agents
from .config import GauntletConfig
from .models import (
    CompetitorTiers,
    DiscoveryPlan,
    MarketAssessment,
    MarketSizing,
    OutreachResults,
    Refutation,
    SharpenedHypothesis,
    SolutionConcept,
    TrendAnalysis,
    ValidatedHypothesis,
)
from .runner import run_agent


def _with_feedback(prompt: str, feedback: list[str] | None) -> str:
    """Append a gate's `missing` list to a stage prompt on retry."""
    if not feedback:
        return prompt
    bullets = "\n".join(f"- {m}" for m in feedback)
    return (
        f"{prompt}\n\nA prior attempt failed the gate. Fix specifically these gaps "
        f"this time:\n{bullets}"
    )


# --------------------------------------------------------------------------- #
# Stage 1 — Problem hypothesis (two sequential subagents)
# --------------------------------------------------------------------------- #
async def stage_hypothesis(
    idea: str, config: GauntletConfig, feedback: list[str] | None = None
) -> ValidatedHypothesis:
    # (a) definer: raw idea -> sharpened, testable hypothesis
    sharpened = await run_agent(
        spec=agents.DEFINER,
        prompt=_with_feedback(f"Raw idea:\n{idea}", feedback),
        schema=SharpenedHypothesis,
        config=config,
    )
    assert isinstance(sharpened, SharpenedHypothesis)

    # (b) pressure-tester: sees ONLY the hypothesis, tries to refute it
    refutation = await run_agent(
        spec=agents.PRESSURE_TESTER,
        prompt=(
            "Refute this problem hypothesis. Find failed competitors, negative "
            f"signals, and structural obstacles.\n\n{sharpened.model_dump_json(indent=2)}"
        ),
        schema=Refutation,
        config=config,
    )
    assert isinstance(refutation, Refutation)

    # Merge the two typed outputs into the stage handoff.
    disconfirming = (
        refutation.failed_competitors
        + refutation.negative_signals
        + refutation.structural_obstacles
    )
    return ValidatedHypothesis(
        statement=sharpened.statement,
        who=sharpened.who,
        how_often=sharpened.how_often,
        how_severe=sharpened.how_severe,
        current_workaround=sharpened.current_workaround,
        is_specific=sharpened.is_specific,
        survived_attack=refutation.survived_attack,
        attack_summary=refutation.attack_summary,
        disconfirming_evidence=disconfirming,
    )


# --------------------------------------------------------------------------- #
# Stage 2 — Market & competition (3 INDEPENDENT subagents in parallel)
# --------------------------------------------------------------------------- #
async def stage_market(
    hyp: ValidatedHypothesis, config: GauntletConfig, feedback: list[str] | None = None
) -> MarketAssessment:
    hyp_json = hyp.model_dump_json(indent=2)
    base = f"Validated hypothesis:\n{hyp_json}"

    # Three independent analyses run concurrently — no shared context between them.
    competitors, sizing, trends = await asyncio.gather(
        run_agent(
            spec=agents.COMPETITOR_TIERING,
            prompt=_with_feedback(base, feedback),
            schema=CompetitorTiers,
            config=config,
        ),
        run_agent(
            spec=agents.TAM_SIZING,
            prompt=_with_feedback(base, feedback),
            schema=MarketSizing,
            config=config,
        ),
        run_agent(
            spec=agents.TREND_ANALYSIS,
            prompt=_with_feedback(base, feedback),
            schema=TrendAnalysis,
            config=config,
        ),
    )

    # Synthesis sees ONLY the three structured analyses (not the hypothesis chat).
    merged = await run_agent(
        spec=agents.MARKET_SYNTHESIS,
        prompt=(
            "Merge these three analyses into one MarketAssessment. Carry the "
            f"hypothesis forward as hypothesis_recap.\n\nHYPOTHESIS:\n{hyp_json}\n\n"
            f"COMPETITORS:\n{competitors.model_dump_json(indent=2)}\n\n"
            f"SIZING:\n{sizing.model_dump_json(indent=2)}\n\n"
            f"TRENDS:\n{trends.model_dump_json(indent=2)}"
        ),
        schema=MarketAssessment,
        config=config,
    )
    assert isinstance(merged, MarketAssessment)
    return merged


# --------------------------------------------------------------------------- #
# Stage 3 — Customer discovery
# --------------------------------------------------------------------------- #
async def stage_discovery(
    market: MarketAssessment, config: GauntletConfig, feedback: list[str] | None = None
) -> DiscoveryPlan:
    plan = await run_agent(
        spec=agents.DISCOVERY_DESIGNER,
        prompt=_with_feedback(
            "Design customer discovery from this market assessment. Carry the "
            f"hypothesis forward as hypothesis_recap.\n\n{market.model_dump_json(indent=2)}",
            feedback,
        ),
        schema=DiscoveryPlan,
        config=config,
    )
    assert isinstance(plan, DiscoveryPlan)
    return plan


# --------------------------------------------------------------------------- #
# Stage 4 — Outreach & scheduling (ASYNC pause/resume, skippable)
# --------------------------------------------------------------------------- #
async def stage_outreach(
    plan: DiscoveryPlan, config: GauntletConfig, feedback: list[str] | None = None
) -> OutreachResults:
    """Outreach is a pause/resume boundary that waits on REAL interview data, so
    it is skippable. When skipped (or in --mock), we synthesize plausible findings
    from the discovery plan so stages 5 can still run end-to-end.
    """
    if config.mock or not config.run_stage4:
        # Synthesize from the plan rather than calling the SDK.
        personas = ", ".join(f.persona for f in plan.frameworks) or "target users"
        return OutreachResults(
            skipped=True,
            prospects=[],
            interviews_completed=0,
            tracking_sheet_path=None,
            discovery_findings=[
                f"[SKIPPED stage 4] No real interviews run for personas: {personas}.",
                "Treat downstream solution as provisional until real discovery completes.",
            ],
        )

    # Live path: MCP (Gmail + Calendar) + human-approved sends. This genuinely
    # waits on humans replying and interviews happening, so callers should run it
    # as a long-lived / resumable task rather than a quick synchronous call.
    from .permissions import make_approval_hook

    role = agents.outreach_role(_mcp_config())
    results = await run_agent(
        spec=role,
        prompt=_with_feedback(
            "Run outreach for this discovery plan. Build the prospect list, draft "
            "and (with approval) send outreach, schedule interviews, keep a tracking "
            f"sheet, and report findings ONLY from real responses.\n\n"
            f"{plan.model_dump_json(indent=2)}",
            feedback,
        ),
        schema=OutreachResults,
        config=config,
        extra_allowed_tools=[f"mcp__{s}__*" for s in role.mcp_servers],
        can_use_tool=make_approval_hook(auto_approve=config.auto_approve_sends),
    )
    assert isinstance(results, OutreachResults)
    return results


def _mcp_config() -> dict:
    """Gmail + Google Calendar over MCP. Stdio servers shown; swap for your
    own auth/transport. Only consulted on the live stage-4 path."""
    return {
        "gmail": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gmail"],
        },
        "google-calendar": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-google-calendar"],
        },
    }


# --------------------------------------------------------------------------- #
# Stage 5 — Solution concept
# --------------------------------------------------------------------------- #
async def stage_solution(
    outreach: OutreachResults, config: GauntletConfig, feedback: list[str] | None = None
) -> SolutionConcept:
    concept = await run_agent(
        spec=agents.SOLUTION_CONCEPT,
        prompt=_with_feedback(
            "Design the solution concept grounded in what discovery ACTUALLY "
            "revealed below — not the original assumption. Name the 3 load-bearing "
            f"assumptions.\n\n{outreach.model_dump_json(indent=2)}",
            feedback,
        ),
        schema=SolutionConcept,
        config=config,
    )
    assert isinstance(concept, SolutionConcept)
    return concept
