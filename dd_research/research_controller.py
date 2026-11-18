"""Bounded controller around a single research-loop decision.

This module records a decision and its status only. It never executes the
selected action or treats an unexecuted action as new evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ControllerResult:
    status: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


def run_bounded_research_controller(
    state: Any,
    cycle: Any,
    *,
    step_fn: Callable[..., dict[str, Any]],
    step_context: dict[str, Any],
    max_steps: int = 5,
) -> ControllerResult:
    """Record one decision, then yield control for execution/state refresh.

    max_steps is validated and retained as a safety-budget declaration. This
    version intentionally executes at most one decision per invocation:
    repeating a decision against unchanged state would create false progress.
    """
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")

    action = step_fn(state, cycle, **step_context)
    if not isinstance(action, dict):
        raise TypeError("step_fn must return an action dictionary")

    action = dict(action)
    action["step_index"] = 1
    selected = action.get("highest_value_action") or action.get("action")
    if selected == "request_human_input":
        status, reason = "paused_for_human", action.get("gate_reason") or "Human input required."
    elif selected == "stop":
        status, reason = "stopped", "The next-action policy selected stop."
    else:
        status, reason = "decision_recorded", "One decision recorded; execution and state refresh remain external."

    return ControllerResult(status=status, steps=[action], reason=reason)
