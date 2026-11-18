"""Derive next-action inputs from current ResearchState without inventing evidence."""
from __future__ import annotations
from typing import Any
from .next_action_policy import derive_next_action
from .next_action_state import record_next_action_in_cycle

def _items(state: Any, name: str) -> list[Any]:
    value = getattr(state, name, None)
    if isinstance(value, dict): return list(value.values())
    if isinstance(value, (list, tuple, set)): return list(value)
    return []

def _status(item: Any) -> str:
    return str(item.get("status", "")) if isinstance(item, dict) else str(getattr(item, "status", ""))

def _summary(item: Any) -> str:
    keys = ("finding", "statement", "description", "reason", "title")
    if isinstance(item, dict):
        for key in keys:
            if item.get(key): return str(item[key])
    for key in keys:
        value = getattr(item, key, None)
        if value: return str(value)
    return ""

def summarize_state_for_next_action(state: Any, *, question: str, decision_relevance: str, method_fit: str) -> dict[str, Any]:
    contradictions = _items(state, "contradictions")
    hypotheses = _items(state, "hypotheses")
    evidence = _items(state, "evidence")
    claims = _items(state, "claims")
    unresolved = [x for x in contradictions if _status(x).lower() in {"open", "unresolved", "material", "foundational"}]
    text = "; ".join(v for v in (_summary(x) for x in unresolved) if v)
    return {
        "question": question,
        "decision_relevance": decision_relevance,
        "evidence": f"{len(evidence)} evidence record(s), {len(claims)} claim record(s), {len(hypotheses)} hypothesis record(s), and {len(contradictions)} contradiction record(s) are visible in state.",
        "important_unknown": "Whether the current evidence is sufficient for the decision." if not evidence or not claims else "Whether remaining uncertainty could materially change the conclusion.",
        "method_fit": method_fit,
        "contradiction": text or ("Unresolved contradiction is recorded." if unresolved else None),
        "unresolved_contradiction": bool(unresolved),
        "evidence_gap": not evidence or not claims,
    }

def derive_next_action_from_state(state: Any, *, question: str, decision_relevance: str, method_fit: str, stopping_satisfied: bool = False, human_gate_required: bool = False, gate_reason: str | None = None) -> dict[str, Any]:
    return derive_next_action(
        **summarize_state_for_next_action(state, question=question, decision_relevance=decision_relevance, method_fit=method_fit),
        stopping_satisfied=stopping_satisfied, human_gate_required=human_gate_required, gate_reason=gate_reason
    )

def derive_and_record_next_action_from_state(state: Any, cycle: Any, **kwargs: Any) -> dict[str, Any]:
    action = derive_next_action_from_state(state, **kwargs)
    return dict(record_next_action_in_cycle(state, cycle, action))
