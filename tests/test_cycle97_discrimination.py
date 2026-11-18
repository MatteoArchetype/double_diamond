
from dd_research_runtime.discrimination import (
    EvidenceCandidate, rank_candidates, reject_confirmatory_only
)

def c(cid, disc, rel, indep, transfer, cost, hyps=2):
    return EvidenceCandidate(
        cid, "question", [f"H{i}" for i in range(hyps)],
        disc, rel, indep, transfer, cost, "rationale"
    )

def test_discriminating_candidate_preferred():
    weak = c("E1","low","high","high","high","low")
    strong = c("E2","high","high","high","medium","medium")
    assert rank_candidates([weak,strong])[0].candidate_id == "E2"

def test_confirmatory_only_candidate_rejected():
    candidate = c("E3","high","high","medium","medium","low",hyps=1)
    assert reject_confirmatory_only(candidate)

def test_unknown_discrimination_is_not_selected_as_discriminating():
    candidate = c("E4","unknown","high","high","high","low")
    assert reject_confirmatory_only(candidate)

def test_empty_candidate_set_is_safe():
    assert rank_candidates([]) == []
