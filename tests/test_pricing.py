"""Token → dollar pricing is exact and deterministic (offline, no DB, no API)."""

from __future__ import annotations

from engine.config import Usage
from engine.pricing import PRICES, WEB_SEARCH_USD, cost_usd


def test_opus_cost_is_summed_per_field():
    usage = Usage(
        input_tokens=1_000,
        output_tokens=500,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=2_000,
        web_searches=2,
        calls=3,
    )
    p = PRICES["claude-opus-4-8"]
    expected = round(
        (1_000 * p["input"] + 500 * p["output"] + 2_000 * p["cache_read"]) / 1_000_000
        + 2 * WEB_SEARCH_USD,
        6,
    )
    assert cost_usd("claude-opus-4-8", usage) == expected
    assert expected > 0  # sanity: real tokens cost real money


def test_haiku_is_cheaper_than_opus_for_same_usage():
    usage = Usage(input_tokens=10_000, output_tokens=10_000, calls=1)
    assert cost_usd("claude-haiku-4-5", usage) < cost_usd("claude-opus-4-8", usage)


def test_zero_usage_is_zero_cost():
    assert cost_usd("claude-opus-4-8", Usage.zero()) == 0.0


def test_unknown_model_still_prices_web_search():
    # An unconfigured model shouldn't crash a run; web-search cost is still counted.
    assert cost_usd("some-future-model", Usage(web_searches=3)) == round(3 * WEB_SEARCH_USD, 6)
