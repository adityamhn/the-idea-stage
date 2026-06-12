"""Deterministic, schema-valid fakes for mock mode.

The whole journey (all five stages + every Coach review) must run end-to-end
offline with zero API calls, so each builder returns a real Pydantic object. No
randomness, no network. A handful of WEAK_MARKERS let you steer a demo: drop one
into an idea and the mock surfaces risk-flavored output downstream so you can see
how the UI renders a shaky idea — but nothing is ever eliminated.
"""

from __future__ import annotations

from pydantic import BaseModel

from .models import (
    Assumption,
    Citation,
    CitedPoint,
    Competitor,
    CompetitorLandscape,
    DiscoveryPlan,
    FounderFit,
    GeneratedIdea,
    Hypothesis,
    InterviewFramework,
    LoadBearingAssumption,
    MarketAssessment,
    MarketSizing,
    MarketVerdict,
    OutreachResults,
    PlaybookFlag,
    PressureTestSynthesis,
    Prospect,
    SolutionConcept,
    StageReview,
    TargetProfile,
    Trend,
    TrendAnalysis,
)

WEAK_MARKERS = ("saturated", "nobody wants", "no budget", "no real problem", "weak-idea")


def _looks_weak(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in WEAK_MARKERS)


def mock_sources(role) -> list[Citation]:
    """Deterministic fake sources for research roles in mock mode."""
    if not getattr(role, "web_search", False):
        return []
    return [
        Citation(
            url="https://example.com/market-report",
            title="[MOCK] Mid-market finance tooling report",
            quote="Finance teams spend hours weekly reconciling expenses.",
            published="2026-01",
        ),
        Citation(
            url="https://example.com/competitor-teardown",
            title="[MOCK] Competitor teardown",
            quote="Incumbents bundle reconciliation for existing cardholders.",
        ),
    ]


def mock_chat_reply(messages: list[dict]) -> str:
    """A deterministic devil's-advocate turn for the pressure-test interview."""
    turns = sum(1 for m in messages if m.get("role") == "user")
    if turns <= 1:
        return (
            "[MOCK] I pulled the strongest case against this. Two incumbents already ship "
            "a 'good enough' version for free, which caps willingness to pay. Tell me about "
            "the last time a customer actually paid to solve this — who, and how much?"
        )
    return (
        "[MOCK] That's a stated preference, not a paid one. What did they do the last time "
        "this problem cost them real money — did they switch tools, or just absorb it?"
    )


def mock_output(schema: type[BaseModel], prompt: str) -> BaseModel:
    seed = prompt.strip().replace("\n", " ")[:160] or "an unspecified idea"
    weak = _looks_weak(prompt)

    if schema is Hypothesis:
        cite = Citation(
            url="https://example.com/finance-ops-survey",
            title="[MOCK] Mid-market finance ops survey",
            quote="Teams spend 4+ hrs/week reconciling expenses.",
        )
        return Hypothesis(
            statement=f"[MOCK] {seed}",
            who="Finance managers at mid-market (200-1000 employee) companies",
            how_often="Weekly, during expense reconciliation",
            how_severe="~4 hrs/week of manual rework; delayed month-end close",
            current_workaround="Manual CSV exports re-keyed into the accounting system",
            why_now="Open accounting APIs and AI extraction make this newly tractable.",
            is_specific=not weak,
            sources=[cite],
            key_assumptions=[
                Assumption(
                    kind="willingness_to_pay",
                    claim="Mid-market finance teams will pay for time saved here.",
                    signal=("Weak — incumbents bundle this for free" if weak
                            else "Comparable tools sell at ~$24k ACV"),
                    confidence="weak" if weak else "mixed",
                    sources=[cite],
                ),
                Assumption(
                    kind="recurring_need",
                    claim="The pain recurs every close, not one-off.",
                    signal="Month-end close is monthly and unavoidable.",
                    confidence="strong",
                    sources=[],
                ),
            ],
        )

    if schema is PressureTestSynthesis:
        cite = Citation(
            url="https://example.com/incumbent-bundling",
            title="[MOCK] Incumbents bundle reconciliation",
            quote="Spend tools auto-code the clean majority for free.",
        )
        return PressureTestSynthesis(
            survived=not weak,
            attack_summary=f"[MOCK] Strongest case against: {seed}",
            disconfirming_evidence=[
                CitedPoint(point="Incumbents already solve the easy 80% for free", sources=[cite])
            ],
            unresolved_questions=["Who has actually paid to solve the exception tail, and how much?"],
            suggested_sharpening=(
                "Narrow to the exception tail, not all reconciliation" if weak else ""
            ),
            sources=[cite],
        )

    if schema is CompetitorLandscape:
        cite = Citation(url="https://example.com/competitors", title="[MOCK] Competitor scan",
                        quote="Ramp and Brex bundle expense management for free.")
        return CompetitorLandscape(
            competitors=[
                Competitor(name="Ramp", tier="direct", why_threat="Free, bundled, well-funded",
                           sources=[cite]),
                Competitor(name="Spreadsheets", tier="indirect", why_threat="The 'good enough' default"),
                Competitor(name="Intuit", tier="potential_acquirer", why_threat="Owns the GL"),
                Competitor(name="Bill.com", tier="adjacent", why_threat="One step from this workflow"),
            ],
            strongest_threat=f"[MOCK] A funded incumbent could copy this fast — {seed}",
            sources=[cite],
        )

    if schema is MarketSizing:
        return MarketSizing(
            tam_usd=12_000_000_000,
            sam_usd=2_400_000_000,
            som_usd=120_000_000,
            method="[MOCK] bottom-up: # mid-market firms x ACV",
            key_assumptions=["50k target firms", "$24k ACV", "1% Y3 penetration"],
            sources=[Citation(url="https://example.com/sizing", title="[MOCK] Market size",
                              quote="~50k mid-market firms in the segment.")],
        )

    if schema is TrendAnalysis:
        t_cite = Citation(url="https://example.com/trends", title="[MOCK] Trend report")
        return TrendAnalysis(
            expanding_consolidating_or_mature="expanding",
            trends=[
                Trend(trend="Open accounting APIs maturing", tailwind_or_headwind="tailwind",
                      sources=[t_cite]),
                Trend(trend="Incumbent bundling", tailwind_or_headwind="headwind", sources=[t_cite]),
            ],
        )

    if schema is MarketVerdict:
        return MarketVerdict(
            hypothesis_recap=f"[MOCK] {seed}",
            real_signal=not weak,
            defensible_angle="[MOCK] Native two-way sync incumbents won't prioritize",
            sources=[Citation(url="https://example.com/signal", title="[MOCK] Signal")],
        )

    if schema is MarketAssessment:
        return MarketAssessment(
            hypothesis_recap=f"[MOCK] {seed}",
            competitors=mock_output(CompetitorLandscape, prompt),  # type: ignore[arg-type]
            sizing=mock_output(MarketSizing, prompt),  # type: ignore[arg-type]
            trends=mock_output(TrendAnalysis, prompt),  # type: ignore[arg-type]
            real_signal=not weak,
            defensible_angle="[MOCK] Native two-way sync incumbents won't prioritize",
            sources=[Citation(url="https://example.com/signal", title="[MOCK] Signal")],
        )

    if schema is DiscoveryPlan:
        return DiscoveryPlan(
            hypothesis_recap=f"[MOCK] {seed}",
            target_profiles=[
                TargetProfile(
                    job_titles=["Finance Manager", "Controller"],
                    company_types=["Mid-market SaaS", "Mid-market services"],
                    seniority="Manager / Director",
                    why_acute="They personally own month-end close.",
                )
            ],
            reachable_channels=["r/Accounting", "Controllers Council Slack", "FENG LinkedIn"],
            frameworks=[
                InterviewFramework(
                    persona="Finance Manager",
                    questions=[
                        "Tell me about the last time you reconciled expenses.",
                        "Walk me through what you did the last time the data didn't match.",
                    ],
                    follow_up_probes=["What made that hard?", "What did you do next?"],
                )
            ],
            non_leading=True,
        )

    if schema is OutreachResults:
        return OutreachResults(
            prospects=[
                Prospect(
                    name="Jane Doe",
                    role="Controller",
                    company="Acme",
                    contact="jane@acme.com",
                    draft_email=(
                        "Hi Jane — I'm researching how controllers handle month-end "
                        "expense reconciliation and would love 20 minutes to hear how "
                        "you do it today. Would you be open to a short call this week?"
                    ),
                    status="queued",
                )
            ],
            interview_guide=[
                "Tell me about the last time you reconciled expenses.",
                "Walk me through what you did when the data didn't match.",
            ],
            scheduling_link="",
            interviews_completed=0,
            discovery_findings=[
                "[MOCK] No real interviews yet — solution stays provisional until done.",
            ],
        )

    if schema is SolutionConcept:
        return SolutionConcept(
            concept="[MOCK] A reconciliation layer with native 2-way accounting sync",
            addresses_revealed_problem="Targets the sync gap discovery surfaced, not raw entry",
            assumptions=[
                LoadBearingAssumption(
                    assumption="Accounting platforms expose stable write APIs",
                    what_must_be_true="Top 3 platforms keep public write endpoints",
                    failure_mode="API access revoked -> sync breaks -> no product",
                ),
                LoadBearingAssumption(
                    assumption="Controllers will trust automated writes",
                    what_must_be_true="Audit trail satisfies their controls",
                    failure_mode="Trust gap -> manual double-check -> no time saved",
                ),
                LoadBearingAssumption(
                    assumption="Incumbents won't ship parity fast",
                    what_must_be_true="18+ month window before bundling",
                    failure_mode="Fast follow -> commoditized -> margin collapse",
                ),
            ],
        )

    if schema is StageReview:
        if weak:
            return StageReview(
                summary="[MOCK] This stage surfaced real doubts worth sitting with.",
                what_this_means="The evidence here is thin — pushing forward risks "
                "validating what you hoped rather than what's true.",
                strengths=["The problem is at least clearly stated"],
                risks=[
                    "Refutation found free incumbent workarounds",
                    "Willingness-to-pay looks weak",
                ],
                playbook_flags=[
                    PlaybookFlag(
                        principle="loss-of-objectivity",
                        note="Output leans optimistic given the disconfirming evidence.",
                    )
                ],
                suggested_next="I'd revisit the hypothesis before continuing — but it's "
                "your call.",
            )
        return StageReview(
            summary="[MOCK] Solid result — the core of this stage holds up.",
            what_this_means="You have enough here to take the next step with eyes open.",
            strengths=["Specific who/how-often/how-severe", "Survived a real attack"],
            risks=["Incumbent bundling remains a watch-item"],
            playbook_flags=[],
            suggested_next="Looks reasonable to continue to the next stage.",
        )

    if schema is FounderFit:
        return FounderFit(
            fit_summary="[MOCK] Strong overlap with the founder's edge.",
            unfair_advantages=["Domain depth", "Reliable-agent infrastructure"],
            gaps=["Distribution into this buyer"],
            hard_no_conflicts=[],
            recommended=not weak,
        )

    if schema is GeneratedIdea:
        return GeneratedIdea(
            title="[MOCK] Reliability layer for agent workflows",
            idea="Teams running autonomous agents in production lack trustworthy "
            "observability and eval tooling.",
            rationale="Agents are moving to production faster than reliability tooling.",
            fit_note="Sits squarely on the founder's reliability + evals edge.",
        )

    raise TypeError(f"No mock builder for schema {schema!r}")
