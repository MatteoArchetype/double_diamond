"""One bounded orchestration step for the research agent.

This composes the existing state-derived next-action policy with lifecycle
recording. It records a decision; it does not execute the selected action.
"""
from __future__ import annotations

from typing import Any

from .next_action_from_state import derive_and_record_next_action_from_state


def run_research_loop_step(
    state: Any,
    cycle: Any,
    *,
    question: str,
    decision_relevance: str,
    method_fit: str,
    stopping_satisfied: bool = False,
    human_gate_required: bool = False,
    gate_reason: str | None = None,
) -> dict[str, Any]:
    """Derive and record one bounded next-action decision."""
    if human_gate_required and not (gate_reason and gate_reason.strip()):
        raise ValueError("gate_reason is required when human_gate_required is true")
    return derive_and_record_next_action_from_state(
        state,
        cycle,
        question=question,
        decision_relevance=decision_relevance,
        method_fit=method_fit,
        stopping_satisfied=stopping_satisfied,
        human_gate_required=human_gate_required,
        gate_reason=gate_reason,
    )
