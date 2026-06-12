"""Per-idea recording of every agent/gate call, so nothing is lost.

`run_agent` is the single chokepoint for all SDK/mock calls, so we record there.
The active recorder is held in a `ContextVar`, which means:

* Each idea's `run_idea` binds its own recorder; concurrent ideas don't mix
  because `asyncio.gather` runs each coroutine in a COPIED context.
* The stage-2 parallel sub-agents (also launched via `asyncio.gather`) inherit
  the idea's recorder through that copied context and append to the SAME list
  object — so the definer, pressure-tester, the three market analysts, and every
  gate all land in one ordered trace.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentCall:
    """One isolated subagent or gate invocation and its result."""

    seq: int
    role: str
    is_gate: bool
    prompt: str               # the meaningful input the role saw (handoff content)
    output: dict[str, Any]    # the validated object / verdict, as JSON-able dict


@dataclass
class IdeaRecorder:
    idea: str
    calls: list[AgentCall] = field(default_factory=list)

    def record(self, role: str, is_gate: bool, prompt: str, output: dict[str, Any]) -> None:
        self.calls.append(
            AgentCall(
                seq=len(self.calls) + 1,
                role=role,
                is_gate=is_gate,
                prompt=prompt,
                output=output,
            )
        )


_current: ContextVar[IdeaRecorder | None] = ContextVar("idea_recorder", default=None)


def set_recorder(recorder: IdeaRecorder) -> None:
    """Bind a recorder for the current (idea's) async context."""
    _current.set(recorder)


def record_call(role: str, is_gate: bool, prompt: str, output: dict[str, Any]) -> None:
    """Append a call to the active recorder, if any (no-op when unset)."""
    recorder = _current.get()
    if recorder is not None:
        recorder.record(role, is_gate, prompt, output)
