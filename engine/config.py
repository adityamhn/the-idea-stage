"""Engine configuration and token-usage accounting."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Strong model runs the five stages; the fast model runs the Coach reviews.
DEFAULT_STAGE_MODEL = "claude-opus-4-8"
DEFAULT_COACH_MODEL = "claude-haiku-4-5"


@dataclass(slots=True)
class EngineConfig:
    """How the engine talks to Claude for one run."""

    stage_model: str = DEFAULT_STAGE_MODEL
    coach_model: str = DEFAULT_COACH_MODEL
    mock: bool = False
    # Cap on web-search rounds per research agent call (cost control).
    max_web_searches: int = 4
    # Safety bound on tool-loop iterations in the client.
    max_tool_rounds: int = 6
    # Per Anthropic request timeout, so a live stage cannot leave the UI running forever.
    request_timeout_seconds: float = 90.0

    @property
    def api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY")


@dataclass(slots=True)
class Usage:
    """Token accounting for one or more Anthropic calls. Summed per run so the
    billing layer can meter credits against real cost."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    web_searches: int = 0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.web_searches += other.web_searches
        self.calls += other.calls

    @classmethod
    def zero(cls) -> "Usage":
        return cls()

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "web_searches": self.web_searches,
            "calls": self.calls,
        }
