"""Token → dollar pricing for one run.

Usage is captured per call (``engine.config.Usage``); this turns it into a USD cost
so the billing layer can see what an idea actually costs. Rates are list prices per
million tokens. VERIFY against https://www.anthropic.com/pricing before trusting the
numbers for real pricing decisions — they change, and this is the one place to edit.
"""

from __future__ import annotations

from .config import Usage

_PER_MTOK = 1_000_000

# (input, output, cache_write_5m, cache_read) USD per million tokens.
# Source: Anthropic list pricing as of 2026-06 (cache write = 1.25x input, read = 0.1x).
# Update here when prices change.
PRICES: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
}

# Server-side web search: USD per request ($10 / 1,000 searches).
WEB_SEARCH_USD = 0.01


def cost_usd(model: str, usage: Usage) -> float:
    """Dollar cost of ``usage`` billed at ``model``'s rate. Unknown models cost 0 but
    raise nothing — callers pass a configured model, and a missing entry should surface
    as a visibly-zero cost rather than crash a run."""
    p = PRICES.get(model)
    if p is None:
        return round(usage.web_searches * WEB_SEARCH_USD, 6)
    total = (
        usage.input_tokens * p["input"]
        + usage.output_tokens * p["output"]
        + usage.cache_creation_input_tokens * p["cache_write"]
        + usage.cache_read_input_tokens * p["cache_read"]
    ) / _PER_MTOK
    total += usage.web_searches * WEB_SEARCH_USD
    return round(total, 6)
