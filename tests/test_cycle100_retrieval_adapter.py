import pytest
from retrieval_adapter import RetrievedDocument


def make_doc(**overrides):
    data = dict(
        source_id="src-1",
        title="Example source",
        publisher="Example publisher",
        url="https://example.org/report",
        retrieved_at="2026-10-02T08:00:00+00:00",
        published_at="2026-09-30",
        passage="Bounded source passage.",
        content_location="p. 4, section 2",
        provenance="external",
        independence_cluster="cluster-1",
    )
    data.update(overrides)
    return RetrievedDocument(**data)


def test_retrieved_document_validates_required_metadata():
    make_doc().validate()


def test_invalid_url_is_rejected():
    with pytest.raises(ValueError, match="HTTP"):
        make_doc(url="not-a-url").validate()


def test_synthetic_document_requires_synthetic_provenance():
    with pytest.raises(ValueError, match="synthetic provenance"):
        make_doc(synthetic=True, provenance="external").validate()


def test_evidence_conversion_preserves_exact_location_without_interpretation():
    payload = make_doc().to_evidence_payload()
    assert payload["source_id"] == "src-1"
    assert payload["finding"] == "Bounded source passage."
    assert payload["location"] == "p. 4, section 2"
    assert "claim" not in payload
    assert "interpretation" not in payload
    assert "hypothesis" not in payload


def test_synthetic_status_and_independence_are_preserved():
    payload = make_doc(
        synthetic=True,
        provenance="synthetic_test",
        independence_cluster="synthetic-cluster",
    ).to_evidence_payload()
    assert payload["synthetic"] is True
    assert payload["provenance"] == "synthetic_test"
    assert payload["independence_cluster"] == "synthetic-cluster"
