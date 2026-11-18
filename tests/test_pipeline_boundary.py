from retrieval_adapter import RetrievedDocument
from research_pipeline import (
    retrieve_to_evidence,
    assess_claim_evidence,
    disposition_claim,
)


def _doc():
    return RetrievedDocument(
        source_id="synthetic-cycle101",
        title="Synthetic pipeline fixture",
        publisher="Test Fixture",
        url="https://example.org/cycle101",
        retrieved_at="2026-10-03T00:00:00Z",
        passage="Bounded finding used only to test the pipeline.",
        content_location="p. 2, paragraph 3",
        provenance="synthetic_test",
        synthetic=True,
        independence_cluster="synthetic-cluster",
    )


def test_retrieval_to_evidence_preserves_boundary():
    payload = retrieve_to_evidence(_doc())
    assert payload["finding"] == "Bounded finding used only to test the pipeline."
    assert payload["location"] == "p. 2, paragraph 3"
    assert payload["synthetic"] is True
    assert "interpretation" not in payload
    assert "claim" not in payload


def test_assessment_and_disposition_chain():
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
    assessment = assess_claim_evidence(
        "ev-101", "claim-101", dimensions, [], "Synthetic test assessment."
    )
    assert assessment["claim_id"] == "claim-101"
    assert assessment["evidence_id"] == "ev-101"

    disposition = disposition_claim(
        "claim-101",
        "retain_bounded",
        "Retain only within the synthetic test boundary.",
        ["ev-101"],
        "candidate",
        "bounded",
        ["Synthetic evidence cannot support real-world generalisation."],
        "test_only",
    )
    assert disposition["disposition"] == "retain_bounded"
    assert disposition["evidence_ids"] == ["ev-101"]


def test_synthetic_boundary_is_enforced():
    bad = RetrievedDocument(
        source_id="synthetic-cycle101-bad",
        title="Bad fixture",
        publisher="Test Fixture",
        url="https://example.org/bad",
        retrieved_at="2026-10-03T00:00:00Z",
        passage="Bad provenance.",
        content_location="p. 1",
        provenance="web",
        synthetic=True,
    )
    try:
        retrieve_to_evidence(bad)
    except ValueError as exc:
        assert "synthetic provenance" in str(exc)
    else:
        raise AssertionError("Synthetic provenance mismatch was not rejected")
