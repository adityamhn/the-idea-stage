"""Deterministic, schema-valid fakes for `--mock` mode.

The whole point: the FULL pipeline (stages, gates, elimination, retry,
parallelism, ranking) must run end-to-end offline with zero API calls. So the
mock returns real Pydantic objects, and the mock gate makes a deterministic
pass/fail decision so a run produces both winners and eliminations.

Determinism rule for gates: an idea is judged "weak" if any WEAK_MARKER appears
in the stage payload. Stage payloads carry the original idea text forward in
their recap fields, so a marker in the idea propagates and that idea gets
eliminated — while clean ideas sail through. No randomness, no network.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from .models import (
    CompetitorTiers,
    DiscoveryPlan,
    GateVerdict,
    InterviewFramework,
    LoadBearingAssumption,
    MarketAssessment,
    MarketSizing,
    OutreachResults,
    Prospect,
    Refutation,
    SharpenedHypothesis,
    SolutionConcept,
    TargetProfile,
    TrendAnalysis,
    ValidatedHypothesis,
)

# Substrings that make the mock gate fail. Put one of these in an idea to watch
# it get eliminated; leave them out and the idea wins.
WEAK_MARKERS = ("saturated", "nobody wants", "no budget", "no real problem", "weak-idea")


def _looks_weak(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in WEAK_MARKERS)


def mock_gate(stage_name: str, payload_json: str, threshold: int) -> GateVerdict:
    """Deterministic adversarial verdict used in --mock mode."""
    weak = _looks_weak(payload_json)
    score = 35 if weak else 82
    return GateVerdict(
        proceed=score >= threshold,
        score=score,
        missing=(
            [f"{stage_name}: concrete disconfirming-evidence rebuttal", "tighter specificity"]
            if weak
            else []
        ),
        reasoning=(
            f"[MOCK] Detected weakness signal in {stage_name} output."
            if weak
            else f"[MOCK] {stage_name} output clears the bar; no fatal gaps found."
        ),
    )


def mock_stage_output(schema: type[BaseModel], prompt: str) -> BaseModel:
    """Return a schema-valid fake object for a stage subagent.

    `prompt` carries upstream context (incl. the original idea); we echo a slice
    of it into recap fields so weakness markers propagate through the chain.
    """
    seed = prompt.strip().replace("\n", " ")[:160] or "an unspecified idea"

    if schema is SharpenedHypothesis:
        return SharpenedHypothesis(
            statement=f"[MOCK] {seed}",
            who="Finance managers at mid-market (200-1000 employee) companies",
            how_often="Weekly, during expense reconciliation",
            how_severe="~4 hrs/week of manual rework; delayed month-end close",
            current_workaround="Manual CSV exports re-keyed into the accounting system",
            is_specific=True,
        )
    if schema is Refutation:
        weak = _looks_weak(prompt)
        return Refutation(
            survived_attack=not weak,
            attack_summary=f"[MOCK] Strongest counter-case for: {seed}",
            failed_competitors=["ExpenseCo (shut down 2021)"],
            negative_signals=["Incumbents bundle this for free"] if weak else [],
            structural_obstacles=["Accounting-software API lock-in"],
        )
    if schema is ValidatedHypothesis:
        weak = _looks_weak(prompt)
        return ValidatedHypothesis(
            statement=f"[MOCK] {seed}",
            who="Finance managers at mid-market companies",
            how_often="Weekly",
            how_severe="~4 hrs/week of rework",
            current_workaround="Manual CSV re-keying",
            survived_attack=not weak,
            attack_summary=f"[MOCK] counter-case for {seed}",
            disconfirming_evidence=(["Incumbents bundle this"] if weak else []),
        )

    if schema is CompetitorTiers:
        return CompetitorTiers(
            direct=["Ramp", "Brex"],
            indirect=["Spreadsheets", "Concur"],
            potential_acquirers=["Intuit", "Sage"],
            adjacent=["Bill.com"],
            strongest_threat=f"[MOCK] A funded incumbent could copy this fast — {seed}",
        )
    if schema is MarketSizing:
        return MarketSizing(
            tam_usd=12_000_000_000,
            sam_usd=2_400_000_000,
            som_usd=120_000_000,
            method="[MOCK] bottom-up: # mid-market firms x ACV",
            key_assumptions=["50k target firms", "$24k ACV", "1% Y3 penetration"],
            model_path=None,
        )
    if schema is TrendAnalysis:
        return TrendAnalysis(
            expanding_consolidating_or_mature="expanding",
            trends=["Real-time accounting mandates", "Embedded-finance APIs", "AI bookkeeping"],
            tailwinds=["Open accounting APIs maturing"],
            headwinds=["Incumbent bundling"],
        )
    if schema is MarketAssessment:
        weak = _looks_weak(prompt)
        return MarketAssessment(
            hypothesis_recap=f"[MOCK] {seed}",
            competitors=mock_stage_output(CompetitorTiers, prompt),  # type: ignore[arg-type]
            sizing=mock_stage_output(MarketSizing, prompt),  # type: ignore[arg-type]
            trends=mock_stage_output(TrendAnalysis, prompt),  # type: ignore[arg-type]
            real_signal=not weak,
            defensible_angle="[MOCK] Native two-way sync incumbents won't prioritize",
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
            skipped=True,
            prospects=[
                Prospect(name="Jane Doe", role="Controller", company="Acme", status="interviewed")
            ],
            interviews_completed=6,
            tracking_sheet_path=None,
            discovery_findings=[
                "[MOCK] Real pain is the 2-way sync, not data entry per se.",
                "[MOCK] Buyers are controllers, not the managers we assumed.",
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

    # Fallback: build from JSON schema defaults (should not be hit for known models).
    raise TypeError(f"No mock builder for schema {schema!r}")


def mock_dispatch(schema: type[BaseModel], prompt: str, *, is_gate: bool, threshold: int,
                  stage_name: str) -> BaseModel:
    """Single entry point the runner calls in --mock mode."""
    if is_gate:
        return mock_gate(stage_name, prompt, threshold)
    return mock_stage_output(schema, prompt)


def to_json(obj: Any) -> str:
    """Compact JSON of a Pydantic object (used to build downstream prompts)."""
    if isinstance(obj, BaseModel):
        return obj.model_dump_json(indent=2)
    return json.dumps(obj, indent=2, default=str)
