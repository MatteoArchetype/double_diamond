from dataclasses import dataclass, asdict
from typing import List

@dataclass
class ContradictionAssessment:
    contradiction_id: str
    claim_id: str
    evidence_ids: List[str]
    issue: str
    comparability: str
    assessment: str
    consequence: str
    next_action: str
    audit_trail: List[str]
    def to_dict(self): return asdict(self)

def assess_contradiction(contradiction_id, claim_id, evidence_ids, issue,
                         comparability, assessment, consequence, next_action,
                         audit_trail):
    if len(evidence_ids) < 2: raise ValueError('A contradiction requires at least two evidence items')
    if not all(x and x.strip() for x in [issue, comparability, assessment, consequence, next_action]):
        raise ValueError('Contradiction assessment fields cannot be blank')
    if not audit_trail: raise ValueError('Contradiction requires an audit trail')
    return ContradictionAssessment(contradiction_id, claim_id, list(evidence_ids), issue,
        comparability, assessment, consequence, next_action, list(audit_trail))

def contradiction_consequence(a):
    if a.assessment in {'unresolved','material_difference'}: return 'claim_cannot_be_unqualified'
    if a.assessment in {'context_difference','definition_difference','timing_difference','method_difference'}:
        return 'claim_must_be_bounded_or_qualified'
    return 'no_special_constraint'
