"""Lifecycle-safe next-action decision boundary."""

from __future__ import annotations
from typing import Any, Mapping

ALLOWED_ACTIONS = {"search", "retrieve", "compare", "audit", "test", "reframe", "synthesise", "request_human_input", "stop"}


def make_next_action(*, question: str, decision_relevance: str, evidence: str,
                     important_unknown: str, contradiction: str | None,
                     highest_value_action: str, method_fit: str,
                     gate_required: bool = False, gate_reason: str | None = None) -> dict[str, Any]:
    if not question.strip(): raise ValueError("question is required")
    if not decision_relevance.strip(): raise ValueError("decision_relevance is required")
    if not evidence.strip(): raise ValueError("evidence is required")
    if not important_unknown.strip(): raise ValueError("important_unknown is required")
    if not method_fit.strip(): raise ValueError("method_fit is required")
    if highest_value_action not in ALLOWED_ACTIONS: raise ValueError(f"unsupported action: {highest_value_action}")
    if gate_required:
        if highest_value_action != "request_human_input": raise ValueError("a required human gate must route the next action to request_human_input")
        if not gate_reason or not gate_reason.strip(): raise ValueError("gate_reason is required when gate_required=True")
    elif gate_reason:
        raise ValueError("gate_reason must be omitted when no gate is required")
    return {"question": question, "decision_relevance": decision_relevance, "evidence": evidence,
            "important_unknown": important_unknown, "contradiction": contradiction,
            "highest_value_action": highest_value_action, "method_fit": method_fit,
            "gate_required": gate_required, "gate_reason": gate_reason}


def record_next_action(state: Any, action: Mapping[str, Any]) -> Mapping[str, Any]:
    if not hasattr(state, "_change"): raise TypeError("state must expose _change")
    state._change("next_action_decision", action.get("evidence", ""), dict(action))
    return action


def record_next_action_in_cycle(state: Any, cycle: Any, action: Mapping[str, Any]) -> Mapping[str, Any]:
    record_next_action(state, action)
    if not hasattr(cycle, "record"): raise TypeError("cycle must expose record")
    cycle.record("next_action", action["highest_value_action"], action["method_fit"])
    return action
