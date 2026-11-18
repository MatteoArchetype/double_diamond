
"""Cycle 98: decision-relevant stopping and escalation."""
from dataclasses import dataclass, asdict
from typing import List

@dataclass
class StoppingAssessment:
    decision_relevance: str
    unresolved_uncertainties: List[str]
    expected_information_gain: str
    potential_to_change_conclusion: str
    evidence_gap_materiality: str
    human_gate_pending: bool
    rationale: str

    def to_dict(self):
        return asdict(self)

def decide(a: StoppingAssessment) -> str:
    if a.human_gate_pending:
        return "escalate_human_gate"

    if a.evidence_gap_materiality == "material" and (
        a.potential_to_change_conclusion in {"high", "unknown"}
    ):
        return "continue_targeted_research"

    if a.expected_information_gain == "high" and (
        a.potential_to_change_conclusion in {"high", "unknown"}
    ):
        return "continue_targeted_research"

    if (
        a.decision_relevance in {"low", "none"}
        and a.evidence_gap_materiality != "material"
    ):
        return "stop_not_decision_relevant"

    if (
        a.evidence_gap_materiality in {"low", "moderate"}
        and a.potential_to_change_conclusion == "low"
    ):
        return "stop_decision_sufficient"

    return "escalate_human_judgement"

def stopping_reason_must_be_recorded(a: StoppingAssessment) -> bool:
    return bool(a.rationale.strip())
