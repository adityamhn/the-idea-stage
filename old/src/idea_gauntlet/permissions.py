"""Human-in-the-loop approval for irreversible stage-4 actions.

Sending an email or creating a calendar invite cannot be undone, so we gate
every such tool call behind explicit human approval using the SDK's
`can_use_tool` permission callback. The callback returns `PermissionResultAllow`
or `PermissionResultDeny`; returning Deny with `interrupt=True` stops the run.

Read-only / drafting tools are allowed automatically — only *sends* prompt.
"""

from __future__ import annotations

from typing import Any, Callable

# Substrings identifying irreversible, outward-facing actions on the MCP tools.
IRREVERSIBLE_HINTS = ("send", "create_event", "create_invite", "delete", "reply")


def _is_irreversible(tool_name: str) -> bool:
    low = tool_name.lower()
    return tool_name.startswith("mcp__") and any(h in low for h in IRREVERSIBLE_HINTS)


def make_approval_hook(auto_approve: bool = False) -> Callable:
    """Build a `can_use_tool` callback.

    `auto_approve=True` is for unattended runs and SKIPS the human prompt — it is
    deliberately off by default because the actions are irreversible.
    """

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any):
        # Imported lazily so mock/offline runs need no SDK installed.
        from claude_agent_sdk.types import (  # type: ignore
            PermissionResultAllow,
            PermissionResultDeny,
        )

        if not _is_irreversible(tool_name):
            return PermissionResultAllow(updated_input=input_data)

        if auto_approve:
            return PermissionResultAllow(updated_input=input_data)

        # Block on a real human. (In a server context, replace this with a
        # queue/await on an out-of-band approval instead of stdin.)
        print("\n*** APPROVAL REQUIRED — irreversible action ***")
        print(f"  tool : {tool_name}")
        print(f"  input: {input_data}")
        answer = input("  Approve this send? [y/N] ").strip().lower()

        if answer == "y":
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(
            message="Human declined this irreversible send.", interrupt=False
        )

    return can_use_tool
