"""Deterministic policy for deriving a bounded next action.

This module converts the current research-state summary into a next-action
record. It deliberately contains no retrieval, browser, causal-inference, or
external-action logic.
"""

from __future__ import annotations

from typing import Any

from .next_action_state import make_next_action, record_next_action_in_cycle


def derive_next_action(
    *,
    question: str,
    decision_relevance: str,
    evidence: str,
    important_unknown: str,
    method_fit: str,
    contradiction: str | None = None,
    unresolved_contradiction: bool = False,
    evidence_gap: bool = False,
    stopping_satisfied: bool = False,
    human_gate_required: bool = False,
    gate_reason: str | None = None,
) -> dict[str, Any]:
    """Select the highest-value bounded action from explicit state signals.

    Priority is intentionally conservative:
      1. human gate
      2. material unresolved contradiction
      3. stopping condition
      4. material evidence gap
      5. synthesis
    """
    if human_gate_required:
        action = "request_human_input"
    elif unresolved_contradiction:
        action = "audit"
    elif stopping_satisfied:
        action = "stop"
    elif evidence_gap:
        action = "retrieve"
    else:
        action = "synthesise"

    return make_next_action(
        question=question,
        decision_relevance=decision_relevance,
        evidence=evidence,
        important_unknown=important_unknown,
        contradiction=contradiction,
        highest_value_action=action,
        method_fit=method_fit,
        gate_required=human_gate_required,
        gate_reason=gate_reason,
    )


def derive_and_record_next_action(
    *,
    state: Any,
    cycle: Any,
    question: str,
    decision_relevance: str,
    evidence: str,
    important_unknown: str,
    method_fit: str,
    contradiction: str | None = None,
    unresolved_contradiction: bool = False,
    evidence_gap: bool = False,
    stopping_satisfied: bool = False,
    human_gate_required: bool = False,
    gate_reason: str | None = None,
) -> dict[str, Any]:
    """Derive and record the decision in both lifecycle layers."""
    action = derive_next_action(
        question=question,
        decision_relevance=decision_relevance,
        evidence=evidence,
        important_unknown=important_unknown,
        method_fit=method_fit,
        contradiction=contradiction,
        unresolved_contradiction=unresolved_contradiction,
        evidence_gap=evidence_gap,
        stopping_satisfied=stopping_satisfied,
        human_gate_required=human_gate_required,
        gate_reason=gate_reason,
    )
    return dict(record_next_action_in_cycle(state, cycle, action))
