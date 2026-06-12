"""The one primitive every stage and gate calls: `run_agent`.

It routes a single isolated subagent invocation through the Claude Agent SDK and
returns a validated Pydantic object. In `--mock` mode it short-circuits to a
deterministic stub so nothing touches the network.

SDK wiring worth understanding (the non-obvious bits):

* Context isolation is STRUCTURAL. Each call is a fresh `query()` that registers
  exactly one subagent and invokes it explicitly ("Use the X agent ..."). The
  subagent starts with an empty conversation; the only thing crossing the
  boundary is the prompt string we pass. Upstream reasoning never leaks in.
  (docs: "A subagent's context window starts fresh ... The only channel from
  parent to subagent is the Agent tool's prompt string.")

* Structured outputs. We pass `output_format={"type":"json_schema","schema":
  Model.model_json_schema()}`. The SDK validates and re-prompts on mismatch, and
  the final `ResultMessage` carries `.structured_output`. We then
  `Model.model_validate(...)` it back into a typed object.

* Skill scoping. We set the session-level `skills=[...]` filter to EXACTLY the
  skills this role may use, and also list them in `AgentDefinition.skills` so
  they preload into the subagent. The session filter is the real guard: skills
  not in the list are hidden from the model, so the wrong skill can't leak into
  the wrong subagent. Skills load from the filesystem only, hence
  `setting_sources=["user","project"]` and `cwd=project_root`.

* `"Agent"` must be in `allowed_tools` so subagent invocations auto-approve
  instead of falling through to the permission callback.
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel

from .agents import RoleSpec
from .config import GauntletConfig
from .mock import mock_dispatch
from .trace import record_call


class AgentRunError(RuntimeError):
    """Raised when the SDK cannot produce schema-valid output."""


async def run_agent(
    *,
    spec: RoleSpec,
    prompt: str,
    schema: type[BaseModel],
    config: GauntletConfig,
    extra_allowed_tools: Sequence[str] = (),
    can_use_tool=None,
) -> BaseModel:
    """Run one isolated subagent and return a validated `schema` instance.

    `spec` describes the role (its AgentDefinition factory, model, skills, tools).
    `prompt` is the ONLY thing the subagent sees of the upstream world.
    """
    if config.mock:
        result = mock_dispatch(
            schema,
            prompt,
            is_gate=spec.is_gate,
            threshold=config.gate_threshold,
            stage_name=spec.name,
        )
        # Record the call so the full per-idea trace is captured offline too.
        record_call(spec.name, spec.is_gate, prompt, result.model_dump(mode="json"))
        return result

    # Imported lazily so `--mock` runs (and the smoke test) need no SDK installed.
    from claude_agent_sdk import (  # type: ignore
        AgentDefinition,
        ClaudeAgentOptions,
        ResultMessage,
        query,
    )

    model = config.gate_model if spec.is_gate else config.stage_model
    agent_def = AgentDefinition(
        description=spec.description,
        prompt=spec.system_prompt,
        tools=list(spec.tools),
        # Per-agent skill preload; combined with the session filter below this
        # keeps each subagent scoped to only its own methods.
        skills=list(spec.skills),
        model=model,
        mcpServers=list(spec.mcp_servers) if spec.mcp_servers else None,
    )

    allowed = {"Agent", *spec.tools, *extra_allowed_tools}

    options = ClaudeAgentOptions(
        cwd=str(config.project_root),
        setting_sources=["user", "project"],   # required for filesystem skill discovery
        skills=list(spec.skills),               # session-level scope = this role's skills only
        agents={spec.name: agent_def},
        allowed_tools=sorted(allowed),
        model=model,                            # parent relays cheaply on the same model
        output_format={"type": "json_schema", "schema": schema.model_json_schema()},
        mcp_servers=spec.mcp_server_config or {},
        can_use_tool=can_use_tool,
        max_turns=spec.max_turns,
    )

    # Force explicit delegation to the single registered subagent, then ask the
    # parent to relay its result verbatim into the structured schema.
    framed = (
        f"Use the {spec.name} agent to do the following, then return its result "
        f"as structured output matching the schema exactly — add no analysis of "
        f"your own:\n\n{prompt}"
    )

    structured: dict[str, Any] | None = None
    async for message in query(prompt=framed, options=options):
        if isinstance(message, ResultMessage):
            if message.subtype == "error_max_structured_output_retries":
                raise AgentRunError(
                    f"{spec.name}: model could not produce schema-valid output."
                )
            structured = getattr(message, "structured_output", None)

    if structured is None:
        raise AgentRunError(f"{spec.name}: no structured_output returned.")

    result = schema.model_validate(structured)
    # Record the meaningful input (not the framing wrapper) and the typed result.
    record_call(spec.name, spec.is_gate, prompt, result.model_dump(mode="json"))
    return result
