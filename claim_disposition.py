from dataclasses import dataclass, asdict
from typing import List

DISPOSITIONS = {"retain_bounded","narrow","split","qualify","promote_to_hypothesis","unresolved","withdraw"}

@dataclass
class ClaimDisposition:
    claim_id: str
    disposition: str
    rationale: str
    evidence_ids: List[str]
    prior_status: str
    new_status: str
    material_uncertainties: List[str]
    decision_relevance: str
    review_required: bool = False
    def to_dict(self): return asdict(self)

def make_disposition(claim_id, disposition, rationale, evidence_ids, prior_status, new_status, material_uncertainties, decision_relevance, review_required=False):
    if disposition not in DISPOSITIONS: raise ValueError(f"Unknown disposition: {disposition}")
    if not rationale.strip(): raise ValueError("Disposition rationale is required")
    if not evidence_ids and disposition not in {"unresolved","withdraw"}: raise ValueError("A supported disposition requires evidence IDs")
    if disposition == "withdraw" and new_status not in {"withdrawn","retracted"}: raise ValueError("Withdrawn claims must have a withdrawn/retracted status")
    if disposition == "promote_to_hypothesis" and new_status != "hypothesis": raise ValueError("Promotion must produce hypothesis status")
    return ClaimDisposition(claim_id, disposition, rationale, list(evidence_ids), prior_status, new_status, list(material_uncertainties), decision_relevance, review_required)

def requires_human_review(d, foundational=False, consequential=False):
    return foundational or consequential or d.disposition in {"withdraw","split","promote_to_hypothesis"} or d.review_required
