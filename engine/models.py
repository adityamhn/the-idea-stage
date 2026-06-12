"""Typed handoffs between stages, plus the Coach review.

Every stage returns one of these Pydantic objects (via a structured-output tool
call), never prose. The next stage receives ONLY the previous stage's object, so
each model carries forward a compact recap of the upstream essentials downstream
stages need (e.g. ``hypothesis_recap``). That is what makes output-only handoffs
work: the object is self-sufficient.

Cross-stage chain:
    ValidatedHypothesis -> MarketAssessment -> DiscoveryPlan
                        -> OutreachResults -> SolutionConcept

A few intra-stage models (SharpenedHypothesis, Refutation, the three market
sub-analyses) let each sub-role inside a stage also return a typed object.

There is NO scoring/gate model here by design — progression is user-driven. After
each stage the Coach produces a ``StageReview`` that explains the result in plain
language so the founder can decide whether to continue.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Citations — proof for every external claim (see CLAUDE.md). The model fills
# these from the URLs the web-search tool actually returned; never fabricated.
# --------------------------------------------------------------------------- #
class Citation(BaseModel):
    url: str = Field(..., description="The source URL backing the claim.")
    title: str = Field("", description="Page/article title.")
    quote: str = Field("", description="Short quoted snippet from the source.")
    published: str = Field("", description="Publication date, if known.")


# --------------------------------------------------------------------------- #
# Stage 1 — Problem hypothesis (single, cited, editable)
# --------------------------------------------------------------------------- #
ASSUMPTION_KINDS = (
    "willingness_to_pay",
    "awareness_gap",
    "recurring_need",
    "urgency",
    "reachability",
)


class Assumption(BaseModel):
    """A testable assumption the hypothesis rests on — one of the angles a VC would
    probe (willingness-to-pay, awareness gap, recurring need, urgency, reachability)."""

    kind: str = Field(..., description=f"One of: {', '.join(ASSUMPTION_KINDS)}.")
    claim: str = Field(..., description="What must be true for the idea to work.")
    signal: str = Field(
        ..., description="The current evidence for or against it, stated plainly."
    )
    confidence: str = Field(
        "mixed", description="How strong the current evidence is: strong | mixed | weak."
    )
    sources: list[Citation] = Field(default_factory=list)


class Hypothesis(BaseModel):
    """Stage 1 handoff — ONE sharp, testable, cited problem hypothesis."""

    statement: str = Field(..., description="One-sentence testable problem hypothesis.")
    who: str = Field(..., description="Exactly who experiences this problem.")
    how_often: str = Field(..., description="How frequently they hit it.")
    how_severe: str = Field(..., description="Severity / cost when it occurs.")
    current_workaround: str = Field(..., description="What they do about it today.")
    why_now: str = Field(..., description="Why this is solvable/urgent now, not earlier.")
    key_assumptions: list[Assumption] = Field(
        default_factory=list, description="The load-bearing assumptions to test."
    )
    is_specific: bool = Field(
        ..., description="True only if who/often/severe/workaround are all concrete."
    )
    sources: list[Citation] = Field(
        default_factory=list, description="Sources backing the core problem framing."
    )


# --------------------------------------------------------------------------- #
# Stage 2 — Pressure test (devil's-advocate interview → cited refutation)
# --------------------------------------------------------------------------- #
class CitedPoint(BaseModel):
    point: str = Field(..., description="A concrete disconfirming point.")
    sources: list[Citation] = Field(default_factory=list)


class PressureTestSynthesis(BaseModel):
    """What the synthesis model produces after the interview (no hypothesis echo)."""

    survived: bool = Field(
        ..., description="Did the hypothesis withstand the attack AND the founder's answers?"
    )
    attack_summary: str = Field(..., description="The strongest case against the idea.")
    disconfirming_evidence: list[CitedPoint] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(
        default_factory=list, description="Questions the founder couldn't answer convincingly."
    )
    suggested_sharpening: str = Field(
        "", description="A sharper hypothesis statement if the interview revealed one."
    )
    sources: list[Citation] = Field(default_factory=list)


class PressureTestResult(PressureTestSynthesis):
    """Stage 2 handoff = synthesis + the hypothesis carried forward (set in code)."""

    hypothesis: Hypothesis


# --------------------------------------------------------------------------- #
# Stage 3 — Market & competition (3 parallel analyses + synthesis), cited
# --------------------------------------------------------------------------- #
class Competitor(BaseModel):
    name: str = Field(..., description="A real, named company/product.")
    tier: str = Field(
        ..., description="direct | indirect | potential_acquirer | adjacent."
    )
    why_threat: str = Field(..., description="Why this player is a genuine threat.")
    sources: list[Citation] = Field(default_factory=list)


class CompetitorLandscape(BaseModel):
    competitors: list[Competitor] = Field(default_factory=list)
    strongest_threat: str = Field(
        ..., description="The most compelling argument for why a rival wins, not you."
    )
    sources: list[Citation] = Field(
        default_factory=list, description="Sources backing the strongest-threat case."
    )


class MarketSizing(BaseModel):
    tam_usd: float = Field(..., description="Total addressable market, USD/year.")
    sam_usd: float
    som_usd: float
    method: str = Field(..., description="Bottom-up derivation (entity count × ACV).")
    key_assumptions: list[str] = Field(default_factory=list)
    sources: list[Citation] = Field(
        default_factory=list, description="Sources for the entity counts / ACV / figures."
    )


class Trend(BaseModel):
    trend: str
    tailwind_or_headwind: str = Field(..., description="tailwind | headwind for THIS idea.")
    sources: list[Citation] = Field(default_factory=list)


class TrendAnalysis(BaseModel):
    expanding_consolidating_or_mature: str
    trends: list[Trend] = Field(
        default_factory=list, description="Up to 3 regulatory/tech/demographic trends."
    )


class MarketVerdict(BaseModel):
    """The synthesis model's output — ONLY the top-level judgement. The competitors,
    sizing, and trends are assembled in code from the cited sub-analyses (lossless)."""

    hypothesis_recap: str = Field(..., description="One line carrying the problem forward.")
    real_signal: bool = Field(..., description="Is there genuine market signal?")
    defensible_angle: str = Field(..., description="Why this can win despite rivals.")
    sources: list[Citation] = Field(default_factory=list)


class MarketAssessment(BaseModel):
    """Stage 3 handoff — synthesis of the three parallel analyses."""

    hypothesis_recap: str = Field(
        ..., description="One line carrying the validated problem forward."
    )
    competitors: CompetitorLandscape
    sizing: MarketSizing
    trends: TrendAnalysis
    real_signal: bool = Field(..., description="Is there genuine market signal?")
    defensible_angle: str = Field(..., description="Why this can win despite rivals.")
    sources: list[Citation] = Field(
        default_factory=list, description="Sources backing the signal/angle judgement."
    )


# --------------------------------------------------------------------------- #
# Stage 3 — Customer discovery
# --------------------------------------------------------------------------- #
class InterviewFramework(BaseModel):
    persona: str
    questions: list[str] = Field(
        ..., description="Past-focused, non-leading interview questions."
    )
    follow_up_probes: list[str] = Field(default_factory=list)


class TargetProfile(BaseModel):
    job_titles: list[str] = Field(default_factory=list)
    company_types: list[str] = Field(default_factory=list)
    seniority: str = ""
    why_acute: str = Field("", description="Why this profile feels the problem acutely.")


class DiscoveryPlan(BaseModel):
    """Stage 3 handoff."""

    hypothesis_recap: str
    target_profiles: list[TargetProfile]
    reachable_channels: list[str] = Field(
        ..., description="Communities, events, LinkedIn/Slack groups to reach them."
    )
    frameworks: list[InterviewFramework] = Field(
        ..., description="One interview framework per persona."
    )
    non_leading: bool = Field(
        ..., description="True if questions probe past behaviour, not future intent."
    )


# --------------------------------------------------------------------------- #
# Stage 4 — Outreach (drafts + scheduling; no auto-send)
# --------------------------------------------------------------------------- #
class Prospect(BaseModel):
    name: str
    role: str
    company: str
    contact: str = ""
    draft_email: str = Field("", description="Personalized outreach draft for this prospect.")
    status: str = "queued"  # queued | contacted | scheduled | interviewed


class OutreachResults(BaseModel):
    """Stage 4 handoff. Produces a prospect list with personalized draft emails and
    an interview guide the founder sends themselves (with a scheduling link). When
    no real interviews have happened yet, ``discovery_findings`` flags the solution
    as provisional so stage 5 stays honest."""

    prospects: list[Prospect] = Field(default_factory=list)
    interview_guide: list[str] = Field(
        default_factory=list, description="Questions to ask, copyable into interviews."
    )
    scheduling_link: str = Field("", description="Cal.com/Calendly link to paste into drafts.")
    interviews_completed: int = 0
    discovery_findings: list[str] = Field(
        default_factory=list,
        description="What interviews actually surfaced (or a provisional placeholder).",
    )


# --------------------------------------------------------------------------- #
# Stage 5 — Solution concept
# --------------------------------------------------------------------------- #
class LoadBearingAssumption(BaseModel):
    assumption: str
    what_must_be_true: str
    failure_mode: str = Field(..., description="What happens if this assumption breaks.")


class SolutionConcept(BaseModel):
    """Stage 5 handoff — the final concept."""

    concept: str = Field(..., description="What the solution does, grounded in findings.")
    addresses_revealed_problem: str = Field(
        ..., description="How it maps to what discovery revealed, not the assumption."
    )
    assumptions: list[LoadBearingAssumption] = Field(
        ..., description="The 3 load-bearing assumptions the design depends on most."
    )


# --------------------------------------------------------------------------- #
# Coach review — produced after every stage (replaces the old scoring gate)
# --------------------------------------------------------------------------- #
class PlaybookFlag(BaseModel):
    principle: str = Field(
        ...,
        description="One of: building-vs-validating | premature-scaling | loss-of-objectivity.",
    )
    note: str = Field(..., description="How this stage's output touches that principle.")


class StageReview(BaseModel):
    """The Coach's plain-language read of a stage. Advisory, never a gate."""

    summary: str = Field(..., description="What this stage produced, in plain language.")
    what_this_means: str = Field(..., description="Why it matters for the founder.")
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(
        default_factory=list, description="Gaps / disconfirming evidence to weigh."
    )
    playbook_flags: list[PlaybookFlag] = Field(default_factory=list)
    suggested_next: str = Field(
        ..., description="Advice on continuing or revisiting — the user still decides."
    )


# --------------------------------------------------------------------------- #
# Founder fit + ideation (used from Phase 3; defined now for the typed chain)
# --------------------------------------------------------------------------- #
class FounderFit(BaseModel):
    fit_summary: str
    unfair_advantages: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    hard_no_conflicts: list[str] = Field(default_factory=list)
    recommended: bool = Field(..., description="Worth pursuing given THIS founder?")


class GeneratedIdea(BaseModel):
    title: str
    idea: str = Field(..., description="One-paragraph problem-first idea statement.")
    rationale: str = Field(..., description="Why this is a real opportunity now.")
    fit_note: str = Field(..., description="Why it fits (or stretches) this founder.")
