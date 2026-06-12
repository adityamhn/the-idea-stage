"""idea_gauntlet — a gated multi-agent pipeline for validating startup ideas."""

from .config import GauntletConfig
from .conductor import Eliminated, IdeaResult, run_gauntlet, run_idea

__all__ = ["GauntletConfig", "Eliminated", "IdeaResult", "run_gauntlet", "run_idea"]
