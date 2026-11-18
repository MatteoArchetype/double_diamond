
"""Cycle 97: discriminating evidence selection.

Selection is based on expected uncertainty reduction and claim relevance,
not on ease of retrieval or confirmation value.
"""
from dataclasses import dataclass, asdict
from typing import List

@dataclass
class EvidenceCandidate:
    candidate_id: str
    question: str
    competing_hypotheses: List[str]
    expected_discrimination: str
    relevance: str
    independence_gain: str
    transferability_gain: str
    retrieval_cost: str
    rationale: str

    def to_dict(self):
        return asdict(self)

def rank_candidates(candidates: List[EvidenceCandidate]) -> List[EvidenceCandidate]:
    if not candidates:
        return []
    # Deliberately not a numerical score. Apply lexicographic research rules.
    def key(c):
        levels = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        return (
            levels.get(c.expected_discrimination, 0),
            levels.get(c.relevance, 0),
            levels.get(c.independence_gain, 0),
            levels.get(c.transferability_gain, 0),
            -levels.get(c.retrieval_cost, 0),
        )
    return sorted(candidates, key=key, reverse=True)

def reject_confirmatory_only(candidate: EvidenceCandidate) -> bool:
    """True when a candidate cannot discriminate between live explanations."""
    return (
        len(candidate.competing_hypotheses) < 2
        or candidate.expected_discrimination in {"low", "unknown"}
    )
