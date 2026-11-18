from dataclasses import dataclass, asdict
from typing import Dict, List
DIMENSIONS=("strength","directness","causal_attribution","transferability","independence","recency","context_completeness","claim_fitness","selection_risk","baseline_quality","outcome_validity","systemic_relevance")
@dataclass
class EvidenceAssessment:
    evidence_id:str; claim_id:str; dimensions:Dict[str,str]; limitations:List[str]; rationale:str; assessor:str="agent"; status:str="advisory"
    def to_dict(self): return asdict(self)
def assess(evidence_id, claim_id, dimensions, limitations, rationale):
    missing=[d for d in DIMENSIONS if d not in dimensions]
    if missing: raise ValueError(f"Missing assessment dimensions: {missing}")
    if not rationale.strip(): raise ValueError("Assessment rationale is required")
    return EvidenceAssessment(evidence_id,claim_id,dimensions,limitations,rationale)
def decision_relevance(a):
    critical={"claim_fitness","directness","context_completeness","independence"}
    if any(a.dimensions.get(d) in {"low","unknown"} for d in critical): return "insufficient_for_unqualified_claim"
    if a.limitations: return "usable_with_qualification"
    return "potentially_fit_for_claim"
