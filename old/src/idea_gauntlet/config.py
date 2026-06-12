"""Run-time configuration for the gauntlet.

Models are configurable (strong model for stages, fast/cheap model for the
adversarial gates). Everything the conductor and runner need to know is here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Default model pair. Stages get the strong model; gates get the fast one.
# Override per-run from the CLI (--stage-model / --gate-model).
DEFAULT_STAGE_MODEL = "claude-opus-4-8"
DEFAULT_GATE_MODEL = "claude-sonnet-4-6"

# Project root = the directory that contains the `.claude/skills/` tree. The SDK
# discovers skills relative to `cwd`, so we point it here.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class GauntletConfig:
    # --- models ---------------------------------------------------------- #
    stage_model: str = DEFAULT_STAGE_MODEL
    gate_model: str = DEFAULT_GATE_MODEL

    # --- gate behaviour -------------------------------------------------- #
    gate_threshold: int = 60          # minimum gate score to proceed
    retry_k: int = 0                  # evaluator-optimizer retries before elimination

    # --- execution ------------------------------------------------------- #
    mock: bool = False                # swap the SDK for a deterministic stub
    max_concurrency: int = 4          # ideas processed in parallel

    # --- stage 4 (irreversible side effects) ----------------------------- #
    run_stage4: bool = False          # OFF by default: real sends are irreversible
    auto_approve_sends: bool = False  # if True, skip the human-approval prompt (DANGER)

    project_root: Path = PROJECT_ROOT

    @property
    def api_key(self) -> str | None:
        """ANTHROPIC_API_KEY is read from the environment by the SDK; we only
        surface it here for a friendly pre-flight error in live mode."""
        return os.environ.get("ANTHROPIC_API_KEY")
