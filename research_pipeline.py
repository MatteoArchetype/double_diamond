from __future__ import annotations
from typing import Any, Mapping, Sequence
from retrieval_adapter import RetrievedDocument


def retrieve_to_evidence(document: RetrievedDocument) -> dict[str, Any]:
    """Convert provider-neutral retrieval output into bounded evidence without interpretation."""
    return document.to_evidence_payload()


def assess_claim_evidence(
    evidence_id: str,
    claim_id: str,
    dimensions: Mapping[str, str],
    limitations: Sequence[str],
    rationale: str,
) -> dict[str, Any]:
    from assessment import assess
    return assess(
        evidence_id,
        claim_id,
        dict(dimensions),
        list(limitations),
        rationale,
    ).to_dict()


def disposition_claim(
    claim_id: str,
    disposition: str,
    rationale: str,
    evidence_ids: Sequence[str],
    prior_status: str,
    new_status: str,
    material_uncertainties: Sequence[str],
    decision_relevance: str,
    review_required: bool = False,
) -> dict[str, Any]:
    from claim_disposition import make_disposition
    return make_disposition(
        claim_id,
        disposition,
        rationale,
        list(evidence_ids),
        prior_status,
        new_status,
        list(material_uncertainties),
        decision_relevance,
        review_required,
    ).to_dict()

def retrieve_to_state(
    state: Any,
    document: RetrievedDocument,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    """Normalize retrieved evidence into the runtime or legacy test state."""
    from pipeline_state import record_pipeline_evidence, record_pipeline_event

    payload = retrieve_to_evidence(document)
    eid = evidence_id or document.source_id
    evidence = {
        "evidence_id": eid,
        "source_id": payload["source_id"],
        "finding": payload["finding"],
        "exact_location": payload["location"],
        "provenance": payload["provenance"],
        "synthetic": payload["synthetic"],
        "independence_cluster": payload["independence_cluster"],
        "metadata": payload["metadata"],
    }

    if not evidence["synthetic"]:
        add_source = getattr(state, "add_source", None)
        if callable(add_source):
            add_source({
                "source_id": document.source_id,
                "title": document.title,
                "publisher": document.publisher,
                "url": document.url,
                "retrieved_at": document.retrieved_at,
                "published_at": document.published_at,
                "provenance": document.provenance,
                "independence_cluster": document.independence_cluster,
            })
        else:
            raise TypeError("Non-synthetic evidence requires add_source()")

    record_pipeline_evidence(state, evidence)
    record_pipeline_event(state, "pipeline_retrieve_to_evidence", [eid])
    return evidence


def assess_claim_evidence_to_state(
    state: Any,
    evidence_id: str,
    claim_id: str,
    dimensions: Mapping[str, str],
    limitations: Sequence[str],
    rationale: str,
) -> dict[str, Any]:
    from pipeline_state import record_pipeline_assessment
    assessment = assess_claim_evidence(
        evidence_id, claim_id, dimensions, limitations, rationale
    )
    record_pipeline_assessment(state, assessment)
    return assessment


def disposition_claim_to_state(
    state: Any,
    claim_id: str,
    disposition: str,
    rationale: str,
    evidence_ids: Sequence[str],
    prior_status: str,
    new_status: str,
    material_uncertainties: Sequence[str],
    decision_relevance: str,
    review_required: bool = False,
) -> dict[str, Any]:
    from pipeline_state import record_pipeline_disposition
    result = disposition_claim(
        claim_id,
        disposition,
        rationale,
        evidence_ids,
        prior_status,
        new_status,
        material_uncertainties,
        decision_relevance,
        review_required,
    )

    if claim_id in getattr(state, "claims", {}):
        update_claim = getattr(state, "update_claim", None)
        if not callable(update_claim):
            raise TypeError("State claim exists but update_claim() is unavailable")
        update_claim(
            claim_id,
            {"disposition": disposition, "status": new_status},
            rationale,
            result.get("cycle_id", "pipeline"),
        )

    record_pipeline_disposition(state, result)
    return result
