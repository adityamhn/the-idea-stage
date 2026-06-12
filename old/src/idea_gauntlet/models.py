"""Typed handoffs between stages.

Every stage boundary is a Pydantic model. Stages RETURN one of these objects
(via the SDK's structured outputs), never prose. The downstream stage receives
ONLY the previous stage's object — so each model deliberately carries forward a
compact recap of the upstream essentials its successors need. That is what makes
"output-only handoffs" actually work: the object is self-sufficient.

Cross-stage chain:
    ValidatedHypothesis -> MarketAssessment -> DiscoveryPlan
                        -> OutreachResults -> SolutionConcept

A few small *intra*-stage models (SharpenedHypothesis, Refutation, and the three
market sub-analyses) exist so each subagent inside a stage also returns a typed
object rather than prose.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Stage 1 — Problem hypothesis
# --------------------------------------------------------------------------- #
class SharpenedHypothesis(BaseModel):
    """Output of the *definer* subagent: the raw idea turned into ONE testable
    hypothesis answering who / how often / how severe / current workaround."""

    statement: str = Field(..., description="One-sentence testable hypothesis.")
    who: str = Field(..., description="Exactly who experiences this problem.")
    how_often: str = Field(..., description="Frequency they encounter it.")
    how_severe: str = Field(..., description="Severity / cost when it occurs.")
    current_workaround: str = Field(..., description="What they do about it today.")
    is_specific: bool = Field(
        ..., description="True only if who/often/severe/workaround are all concrete."
    )


class Refutation(BaseModel):
    """Output of the *pressure-tester* subagent, which sees ONLY the hypothesis
    and is told to refute it."""

    survived_attack: bool = Field(
        ..., description="True if the hypothesis withstands the strongest counter-case."
    )
    attack_summary: str = Field(..., description="The strongest case against the idea.")
    failed_competitors: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    structural_obstacles: list[str] = Field(default_factory=list)


class ValidatedHypothesis(BaseModel):
    """Stage 1 handoff = sharpened hypothesis + its refutation."""

    statement: str
    who: str
    how_often: str
    how_severe: str
    current_workaround: str
    is_specific: bool
    survived_attack: bool
    attack_summary: str
    disconfirming_evidence: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Stage 2 — Market & competition (3 parallel analyses + synthesis)
# --------------------------------------------------------------------------- #
class CompetitorTiers(BaseModel):
    direct: list[str] = Field(default_factory=list)
    indirect: list[str] = Field(default_factory=list)
    potential_acquirers: list[str] = Field(default_factory=list)
    adjacent: list[str] = Field(default_factory=list)
    strongest_threat: str = Field(
        ..., description="The most compelling argument for why a rival wins, not you."
    )


class MarketSizing(BaseModel):
    tam_usd: float = Field(..., description="Total addressable market, USD/year.")
    sam_usd: float
    som_usd: float
    method: str = Field(..., description="How the numbers were derived (bottom-up etc.).")
    key_assumptions: list[str] = Field(default_factory=list)
    model_path: str | None = Field(
        default=None, description="Path to a generated xlsx model, if any."
    )


class TrendAnalysis(BaseModel):
    expanding_consolidating_or_mature: str
    trends: list[str] = Field(
        ..., description="Up to 3 regulatory/technological/demographic trends."
    )
    tailwinds: list[str] = Field(default_factory=list)
    headwinds: list[str] = Field(default_factory=list)


class MarketAssessment(BaseModel):
    """Stage 2 handoff — synthesis of the three parallel analyses."""

    hypothesis_recap: str = Field(
        ..., description="One line carrying the validated problem forward."
    )
    competitors: CompetitorTiers
    sizing: MarketSizing
    trends: TrendAnalysis
    real_signal: bool = Field(..., description="Is there genuine market signal?")
    defensible_angle: str = Field(..., description="Why this can win despite rivals.")


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
# Stage 4 — Outreach & scheduling (async / skippable)
# --------------------------------------------------------------------------- #
class Prospect(BaseModel):
    name: str
    role: str
    company: str
    contact: str = ""
    status: str = "queued"  # queued | contacted | scheduled | interviewed


class OutreachResults(BaseModel):
    """Stage 4 handoff. In skip/mock mode `interviews_completed` is synthesized so
    the rest of the pipeline can run; `discovery_findings` is what stage 5 keys off
    — i.e. what discovery ACTUALLY revealed, not the original assumption."""

    skipped: bool = Field(
        default=False, description="True when stage 4 ran in mock/skip mode."
    )
    prospects: list[Prospect] = Field(default_factory=list)
    interviews_completed: int = 0
    tracking_sheet_path: str | None = None
    discovery_findings: list[str] = Field(
        ..., description="What the interviews actually surfaced (the real signal)."
    )


# --------------------------------------------------------------------------- #
# Stage 5 — Solution concept (winner if reached & passed)
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
# Gate verdict — emitted by the adversarial judge between every stage
# --------------------------------------------------------------------------- #
class GateVerdict(BaseModel):
    proceed: bool
    score: int = Field(..., ge=0, le=100, description="Confidence this stage passed.")
    missing: list[str] = Field(
        default_factory=list,
        description="What is absent/weak — fed back to the stage on retry.",
    )
    reasoning: str
