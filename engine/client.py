"""The single Anthropic chokepoint.

Every stage sub-role and the Coach go through ``run_agent``. It builds one Messages
call from a Role: the role's system prompt + its scoped skill modules (prompt-cached),
an output tool whose schema is the target Pydantic model, and — for research roles —
the server-side web-search tool. It runs a small loop to extract the structured
output, validates it into the Pydantic model, and returns it with token usage.

In mock mode it never touches the network: it returns deterministic, schema-valid
objects so the whole journey runs offline with zero API calls.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .config import EngineConfig, Usage
from .models import Citation
from .roles import Role, load_skill

T = TypeVar("T", bound=BaseModel)

# A static instruction shared by every research role's system prompt tail.
_EMIT_NOTE = (
    "\n\nWhen you have everything you need, return the final answer by calling the "
    "'{tool}' tool exactly once with well-formed arguments. Do not write prose after."
)


class AgentError(RuntimeError):
    """The model did not produce a valid structured output within the round budget."""


def _build_system(role: Role, tool_name: str) -> list[dict]:
    """System as cacheable text blocks: role prompt first, then each skill module.
    The last static block carries ``cache_control`` so the whole prefix is cached.
    Pass an empty ``tool_name`` for free-text (chat) turns to skip the emit note."""
    head = role.system_prompt + (_EMIT_NOTE.format(tool=tool_name) if tool_name else "")
    blocks: list[dict] = [{"type": "text", "text": head}]
    for skill in role.skills:
        blocks.append({"type": "text", "text": f"# Skill: {skill}\n\n{load_skill(skill)}"})
    if len(blocks) > 1:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def _output_tool(schema: type[BaseModel]) -> dict:
    return {
        "name": schema.__name__,
        "description": f"Return the result as a well-formed {schema.__name__}.",
        "input_schema": schema.model_json_schema(),
    }


def _find_tool_use(content, tool_name: str):
    for block in content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block
    return None


def _collect_sources(content, into: dict[str, Citation]) -> None:
    """Accumulate real sources from a response's content blocks, deduped by URL.

    Two places carry them: `web_search_tool_result` blocks (the pages the tool
    returned) and text-block `citations` of type `web_search_result_location`
    (the per-claim quotes Claude actually used). Quotes from the latter win.
    """
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "web_search_tool_result":
            for item in getattr(block, "content", None) or []:
                url = getattr(item, "url", None)
                if not url:
                    continue  # error items have no url
                into.setdefault(
                    url,
                    Citation(
                        url=url,
                        title=getattr(item, "title", "") or "",
                        published=getattr(item, "page_age", "") or "",
                    ),
                )
        elif btype == "text":
            for cit in getattr(block, "citations", None) or []:
                url = getattr(cit, "url", None)
                if not url:
                    continue
                quote = getattr(cit, "cited_text", "") or ""
                existing = into.get(url)
                if existing is None:
                    into[url] = Citation(
                        url=url, title=getattr(cit, "title", "") or "", quote=quote
                    )
                elif quote and not existing.quote:
                    existing.quote = quote


def _collect_usage(resp) -> Usage:
    u = resp.usage
    web = 0
    server = getattr(u, "server_tool_use", None)
    if server is not None:
        web = getattr(server, "web_search_requests", 0) or 0
    return Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        web_searches=web,
        calls=1,
    )


def _client(config: EngineConfig):
    if not config.api_key:
        raise AgentError("ANTHROPIC_API_KEY is not set (and config.mock is False).")
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=config.api_key, timeout=config.request_timeout_seconds)


def _web_tool(config: EngineConfig) -> dict:
    return {"type": "web_search_20250305", "name": "web_search",
            "max_uses": config.max_web_searches}


async def run_agent(
    *,
    role: Role,
    prompt: str,
    schema: type[T],
    config: EngineConfig,
) -> tuple[T, list[Citation], Usage]:
    """Run one role and return (typed output, sources consulted, token usage)."""
    if config.mock:
        from .mock import mock_output, mock_sources

        return mock_output(schema, prompt), mock_sources(role), Usage.zero()

    client = _client(config)
    tool_name = schema.__name__
    model = config.coach_model if role.is_coach else config.stage_model
    max_tokens = 2048 if role.is_coach else 8192

    system = _build_system(role, tool_name)
    tools: list[dict] = [_output_tool(schema)]
    if role.web_search:
        tools.append(_web_tool(config))

    messages: list[dict] = [{"role": "user", "content": prompt}]
    # Force the output tool immediately unless the role may search first.
    tool_choice: dict = (
        {"type": "auto"} if role.web_search else {"type": "tool", "name": tool_name}
    )

    usage = Usage.zero()
    sources: dict[str, Citation] = {}
    for _ in range(config.max_tool_rounds):
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            messages=messages,
        )
        usage.add(_collect_usage(resp))
        _collect_sources(resp.content, sources)

        block = _find_tool_use(resp.content, tool_name)
        if block is not None:
            try:
                return schema.model_validate(block.input), list(sources.values()), usage
            except ValidationError as exc:
                # A tool_use MUST be answered with a tool_result in the next message.
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "is_error": True,
                        "content": f"Invalid arguments:\n{exc}\n\nCall '{tool_name}' "
                                   "again with corrected, schema-valid arguments.",
                    }],
                })
                tool_choice = {"type": "tool", "name": tool_name}
                continue

        # No output tool yet. If the model paused mid-search, resume; otherwise nudge.
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":
            continue
        messages.append({
            "role": "user",
            "content": f"Now return the final result by calling the '{tool_name}' tool.",
        })
        tool_choice = {"type": "tool", "name": tool_name}

    raise AgentError(
        f"{role.name}: no valid {tool_name} after {config.max_tool_rounds} rounds."
    )


def _text_of(content) -> str:
    return "".join(getattr(b, "text", "") for b in content if getattr(b, "type", None) == "text")


def _chat_text(content) -> str:
    """The user-visible text of a chat turn. Models narrate their research plan in text
    blocks BEFORE web searches ("Let me check..."); the real message is composed after
    the results land. So when the turn contains searches, keep only text after the last
    search-result block — falling back to the full text if nothing follows."""
    last_search = max(
        (i for i, b in enumerate(content)
         if getattr(b, "type", None) == "web_search_tool_result"),
        default=-1,
    )
    after = _text_of(content[last_search + 1:])
    return after if after.strip() else _text_of(content)


async def run_chat(
    *,
    role: Role,
    messages: list[dict],
    config: EngineConfig,
    web_search: bool = False,
) -> tuple[str, list[Citation], Usage]:
    """A multi-turn, free-text turn (no structured output). Returns the assistant's
    text, the sources it consulted this turn, and usage. Used by the pressure-test
    interview; the final structured conclusion still goes through run_agent."""
    if config.mock:
        from .mock import mock_chat_reply

        return mock_chat_reply(messages), [], Usage.zero()

    client = _client(config)
    tools = [_web_tool(config)] if web_search else []
    system = _build_system(role, tool_name="")

    usage = Usage.zero()
    sources: dict[str, Citation] = {}
    convo = list(messages)
    for _ in range(config.max_tool_rounds):
        resp = await client.messages.create(
            model=config.stage_model,
            max_tokens=2048,
            system=system,
            tools=tools,
            messages=convo,
        )
        usage.add(_collect_usage(resp))
        _collect_sources(resp.content, sources)
        if resp.stop_reason == "pause_turn":
            convo.append({"role": "assistant", "content": resp.content})
            continue
        return _chat_text(resp.content), list(sources.values()), usage

    raise AgentError(f"{role.name}: chat did not complete after {config.max_tool_rounds} rounds.")
