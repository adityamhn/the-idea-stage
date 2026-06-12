"""Role specs: one per subagent the pipeline can spawn.

A `RoleSpec` is a thin, serializable description of a subagent — its system
prompt, the skills it is allowed to load, the tools it may call, and whether it
is an adversarial gate (fast model) or a stage worker (strong model). The runner
turns a `RoleSpec` into an SDK `AgentDefinition` at call time.

Skills are scoped here: each role lists ONLY the skills it should see, so e.g.
the `gate-rubric` never leaks into a stage worker and `interview-design` never
leaks into the market analyst.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

# Built-in tools we reference by their SDK names.
WEB = "WebSearch"
READ, WRITE, BASH, GLOB, GREP = "Read", "Write", "Bash", "Glob", "Grep"

# Tool set a subagent needs to run a skill that ships a script + builds an xlsx.
FILE_TOOLS = [READ, WRITE, BASH, GLOB, GREP]


@dataclass(slots=True)
class RoleSpec:
    name: str
    description: str
    system_prompt: str
    skills: Sequence[str] = field(default_factory=tuple)
    tools: Sequence[str] = field(default_factory=tuple)
    is_gate: bool = False
    max_turns: int | None = None
    # MCP servers this role may use, by name (the config lives on the options).
    mcp_servers: Sequence[str] = field(default_factory=tuple)
    mcp_server_config: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Stage 1 — Problem hypothesis
# --------------------------------------------------------------------------- #
DEFINER = RoleSpec(
    name="definer",
    description="Sharpens a raw startup idea into one testable problem hypothesis.",
    system_prompt=(
        "You are a problem-definition specialist. Turn the raw idea into ONE "
        "testable hypothesis. Force specificity: name exactly WHO has the problem, "
        "HOW OFTEN they hit it, HOW SEVERE it is (time/money), and the CURRENT "
        "WORKAROUND. Reject vague observations. Use the hypothesis-sharpening "
        "skill. Set is_specific=false if any field is still generic."
    ),
    skills=("hypothesis-sharpening",),
    tools=(WEB,),
)

PRESSURE_TESTER = RoleSpec(
    name="pressure-tester",
    description="Adversarially refutes a problem hypothesis with disconfirming evidence.",
    system_prompt=(
        "You are a ruthless devil's advocate. You receive ONLY a problem "
        "hypothesis — not the founder's reasoning. Your job is to REFUTE it: hunt "
        "for failed competitors, negative market signals, and structural obstacles "
        "that a supportive synthesis would bury. Use the devils-advocate skill. "
        "Only set survived_attack=true if the hypothesis genuinely withstands the "
        "strongest counter-case you can build."
    ),
    skills=("devils-advocate",),
    tools=(WEB,),
)


# --------------------------------------------------------------------------- #
# Stage 2 — Market & competition (3 parallel + synthesis)
# --------------------------------------------------------------------------- #
COMPETITOR_TIERING = RoleSpec(
    name="competitor-tiering",
    description="Maps the competitive landscape by tier and argues the strongest threat.",
    system_prompt=(
        "You map competitors by tier: direct, indirect, potential acquirers, and "
        "adjacent players who could move in. Counter competitor-neglect: make the "
        "MOST compelling argument for why a rival would succeed while the founder "
        "does not. Use the competitive-tiering skill."
    ),
    skills=("competitive-tiering",),
    tools=(WEB,),
)

TAM_SIZING = RoleSpec(
    name="tam-sizing",
    description="Builds a defensible TAM/SAM/SOM model and pressure-tests its assumptions.",
    system_prompt=(
        "You size the market bottom-up. Build a TAM/SAM/SOM model and STATE every "
        "assumption, then pressure-test it. Use the tam-sam-som skill, which ships "
        "a script that writes a deterministic xlsx model — run it and report the "
        "model_path. Use the xlsx skill if you need to inspect or format the file."
    ),
    skills=("tam-sam-som", "xlsx"),
    tools=tuple(FILE_TOOLS + [WEB]),
)

TREND_ANALYSIS = RoleSpec(
    name="trend-analysis",
    description="Identifies external trends and labels each a tailwind or headwind.",
    system_prompt=(
        "You identify whether the market is expanding, consolidating, or mature, "
        "and surface up to three regulatory/technological/demographic trends that "
        "could move it in the next two years. Label each a tailwind or headwind "
        "for THIS specific hypothesis."
    ),
    skills=(),  # a one-off analysis: instruction lives in the prompt, not a skill
    tools=(WEB,),
)

MARKET_SYNTHESIS = RoleSpec(
    name="market-synthesis",
    description="Merges the three market analyses into one assessment with a defensible angle.",
    system_prompt=(
        "You receive ONLY three structured analyses (competitors, sizing, trends). "
        "Merge them into one assessment. Decide honestly whether there is real "
        "market signal and name the single most defensible angle — or say there "
        "isn't one. Do not invent facts beyond the three inputs."
    ),
    skills=(),
    tools=(),
)


# --------------------------------------------------------------------------- #
# Stage 3 — Customer discovery
# --------------------------------------------------------------------------- #
DISCOVERY_DESIGNER = RoleSpec(
    name="discovery-designer",
    description="Designs target profiles, reachable channels, and per-persona interview guides.",
    system_prompt=(
        "You design customer discovery. Produce a precise target profile (titles, "
        "company types, seniority), where those people are actually reachable, and "
        "a separate interview framework PER persona. Questions must be PAST-focused "
        "and non-leading ('tell me about the last time...'), never future-facing "
        "('would you use...'). Use the interview-design skill. Set non_leading=false "
        "if any question leads the respondent."
    ),
    skills=("interview-design",),
    tools=(WEB,),
)


# --------------------------------------------------------------------------- #
# Stage 4 — Outreach & scheduling (async, MCP, human-approved sends)
# --------------------------------------------------------------------------- #
def outreach_role(mcp_server_config: dict[str, Any]) -> RoleSpec:
    """Stage 4 wires Gmail + Calendar over MCP. Real sends are irreversible, so
    the runner pairs this with a `can_use_tool` approval hook."""
    return RoleSpec(
        name="outreach",
        description="Builds a prospect list, drafts outreach, schedules interviews, tracks status.",
        system_prompt=(
            "You run customer-discovery outreach. From the target profile, build a "
            "prospect list, draft personalized outreach per contact, send via Gmail "
            "(every send requires human approval — do not assume it), and schedule "
            "interviews via Google Calendar. Maintain a tracking sheet with the xlsx "
            "skill. Report discovery_findings ONLY from real interview data."
        ),
        skills=("xlsx",),
        tools=tuple(FILE_TOOLS),
        mcp_servers=("gmail", "google-calendar"),
        mcp_server_config=mcp_server_config,
        max_turns=40,
    )


# --------------------------------------------------------------------------- #
# Stage 5 — Solution concept
# --------------------------------------------------------------------------- #
SOLUTION_CONCEPT = RoleSpec(
    name="solution-concept",
    description="Designs the solution concept and names its 3 load-bearing assumptions.",
    system_prompt=(
        "You design the solution concept grounded in what discovery ACTUALLY "
        "revealed — not the founder's original assumption. State how the concept "
        "maps to the revealed problem. Then name the THREE assumptions the design "
        "depends on most heavily; for each, what must be true and the failure mode "
        "if it doesn't hold."
    ),
    skills=(),
    tools=(WEB,),
)


# --------------------------------------------------------------------------- #
# Gate — adversarial LLM-as-judge (fast model), one per stage boundary
# --------------------------------------------------------------------------- #
def gate_role(stage_key: str) -> RoleSpec:
    """A cheap, adversarial judge. It loads the gate-rubric skill and scores the
    stage output against that stage's exit criteria, hunting for reasons NOT to
    proceed."""
    return RoleSpec(
        name=f"gate-{stage_key}",
        description=f"Adversarial exit-criteria judge for the {stage_key} stage.",
        system_prompt=(
            "You are an adversarial gatekeeper, NOT a cheerleader. You receive one "
            "stage's structured output. Load the gate-rubric skill and score it "
            f"against the exit criteria for the '{stage_key}' stage. Actively hunt "
            "for disconfirming evidence and reasons to STOP. Be stingy: only let "
            "strong, specific, well-evidenced work proceed. Populate `missing` with "
            "the concrete gaps a retry would need to fix. Return a GateVerdict."
        ),
        skills=("gate-rubric",),
        tools=(),
        is_gate=True,
    )
