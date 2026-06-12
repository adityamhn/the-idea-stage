"""Offline smoke test: the whole journey runs in mock mode with zero API calls.

Every stage must return a valid typed output AND a StageReview. No scoring, no
elimination — just that the chain holds and the Coach speaks at each step.
"""

from __future__ import annotations

import pytest

from engine import pressure_test
from engine.conductor import INTERACTIVE_STAGES, STAGE_ORDER, run_stage
from engine.config import EngineConfig
from engine.models import (
    DiscoveryPlan,
    Hypothesis,
    MarketAssessment,
    OutreachResults,
    PressureTestResult,
    SolutionConcept,
    StageReview,
)

EXPECTED_OUTPUT_TYPE = {
    "hypothesis": Hypothesis,
    "pressure_test": PressureTestResult,
    "market": MarketAssessment,
    "discovery": DiscoveryPlan,
    "outreach": OutreachResults,
    "solution": SolutionConcept,
}


@pytest.mark.asyncio
async def test_full_journey_runs_offline():
    config = EngineConfig(mock=True)
    prior: object = "AI expense reconciliation for mid-market finance teams"

    for stage_key in STAGE_ORDER:
        if stage_key in INTERACTIVE_STAGES:
            # Pressure test is interactive: open the interview, answer once, conclude.
            opening, _, _ = await pressure_test.open_interview(prior, config)
            visible = [{"role": "assistant", "text": opening},
                       {"role": "user", "text": "A customer paid $20k last year for this."}]
            result_out, _, _ = await pressure_test.conclude(prior, visible, config)
            assert isinstance(result_out, EXPECTED_OUTPUT_TYPE[stage_key])
            prior = result_out
            continue

        result = await run_stage(stage_key, prior, config, scheduling_link="https://cal.com/x")
        assert result.stage_key == stage_key
        assert isinstance(result.output, EXPECTED_OUTPUT_TYPE[stage_key])
        assert isinstance(result.review, StageReview)
        assert result.review.summary and result.review.suggested_next
        assert result.usage.calls == 0
        prior = result.output


@pytest.mark.asyncio
async def test_hypothesis_is_cited():
    config = EngineConfig(mock=True)
    result = await run_stage("hypothesis", "AI expense reconciliation", config)

    hyp = result.output
    assert isinstance(hyp, Hypothesis)
    assert hyp.sources and hyp.sources[0].url  # every external claim is cited
    assert hyp.key_assumptions  # load-bearing assumptions named


@pytest.mark.asyncio
async def test_weak_idea_surfaces_risks_but_is_not_blocked():
    config = EngineConfig(mock=True)
    # The 'weak-idea' marker steers the deterministic mock toward risk-flavored output.
    result = await run_stage("hypothesis", "a weak-idea nobody wants", config)

    assert isinstance(result.output, Hypothesis)
    assert result.output.is_specific is False
    # Coaching surfaces risk and a playbook flag, but never eliminates.
    assert result.review.risks
    assert result.review.playbook_flags


@pytest.mark.asyncio
async def test_pressure_test_interview_and_conclude():
    config = EngineConfig(mock=True)
    from engine.mock import mock_output

    hyp = mock_output(Hypothesis, "AI expense reconciliation")
    opening, _, _ = await pressure_test.open_interview(hyp, config)
    assert opening  # the interviewer opens with something

    visible = [{"role": "assistant", "text": opening},
               {"role": "user", "text": "We saw 3 customers pay for this."}]
    reply, _, _ = await pressure_test.next_reply(hyp, visible, "They each paid $24k.", config)
    assert reply

    result, _, _ = await pressure_test.conclude(hyp, visible, config)
    assert isinstance(result, PressureTestResult)
    assert result.hypothesis.statement == hyp.statement  # hypothesis carried forward
    assert result.disconfirming_evidence and result.disconfirming_evidence[0].sources


@pytest.mark.asyncio
async def test_outreach_keeps_solution_provisional():
    config = EngineConfig(mock=True)
    from engine.mock import mock_output

    plan = mock_output(DiscoveryPlan, "idea")
    result = await run_stage("outreach", plan, config, scheduling_link="https://cal.com/x")

    out = result.output
    assert isinstance(out, OutreachResults)
    assert out.interviews_completed == 0
    assert out.discovery_findings  # honest provisional note present
