from research_pipeline import (
    retrieve_to_state,
    assess_claim_evidence_to_state,
    disposition_claim_to_state,
)
from retrieval_adapter import RetrievedDocument


class FakeState:
    def __init__(self):
        self.collections = {
            "evidence": [],
            "assessments": [],
            "dispositions": [],
        }


def _doc():
    return RetrievedDocument(
        source_id="synthetic-cycle102",
        title="Synthetic state fixture",
        publisher="Test Fixture",
        url="https://example.org/cycle102",
        retrieved_at="2026-10-03T00:00:00Z",
        passage="State integration fixture.",
        content_location="p. 4, paragraph 1",
        provenance="synthetic_test",
        synthetic=True,
        independence_cluster="synthetic-cycle102",
    )


def test_pipeline_records_artifacts_without_changing_evidence():
    state = FakeState()
    evidence = retrieve_to_state(state, _doc())

    assert len(state.collections["evidence"]) == 1
    assert state.collections["evidence"][0] == evidence
    assert evidence["finding"] == "State integration fixture."
    assert "interpretation" not in evidence


def test_assessment_and_disposition_are_recorded_separately():
    state = FakeState()
    dimensions = {
        "strength": "high",
        "directness": "high",
        "causal_attribution": "high",
        "transferability": "high",
        "independence": "high",
        "recency": "high",
        "context_completeness": "high",
        "claim_fitness": "high",
        "selection_risk": "low",
        "baseline_quality": "high",
        "outcome_validity": "high",
        "systemic_relevance": "high",
    }

    assessment = assess_claim_evidence_to_state(
        state, "ev-102", "claim-102", dimensions, [], "State test."
    )
    disposition = disposition_claim_to_state(
        state,
        "claim-102",
        "retain_bounded",
        "State integration test.",
        ["ev-102"],
        "candidate",
        "bounded",
        ["Synthetic-only fixture."],
        "test_only",
    )

    assert state.collections["assessments"] == [assessment]
    assert state.collections["dispositions"] == [disposition]
    assert state.collections["assessments"][0]["claim_id"] == "claim-102"
    assert state.collections["dispositions"][0]["evidence_ids"] == ["ev-102"]
