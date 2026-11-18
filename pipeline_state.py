from __future__ import annotations

from typing import Any, Mapping


def record_pipeline_evidence(state: Any, evidence: Mapping[str, Any]) -> None:
    add_evidence = getattr(state, "add_evidence", None)
    if callable(add_evidence):
        add_evidence(dict(evidence))
        return

    collections = getattr(state, "collections", None)
    if isinstance(collections, dict) and isinstance(collections.get("evidence"), list):
        collections["evidence"].append(dict(evidence))
        return

    raise TypeError("State does not expose add_evidence() or a compatible evidence collection")


def record_pipeline_assessment(state: Any, assessment: Mapping[str, Any]) -> None:
    collections = getattr(state, "collections", None)
    if isinstance(collections, dict) and isinstance(collections.get("assessments"), list):
        collections["assessments"].append(dict(assessment))
        return
    # ResearchState deliberately has no first-class assessment collection;
    # callers should retain the returned assessment artifact and cycle-log it.
    record_pipeline_event(
        state,
        "pipeline_assessment",
        [assessment["evidence_id"], assessment["claim_id"]],
        assessment.get("disposition", "assessed"),
    )


def record_pipeline_disposition(state: Any, disposition: Mapping[str, Any]) -> None:
    collections = getattr(state, "collections", None)
    if isinstance(collections, dict) and isinstance(collections.get("dispositions"), list):
        collections["dispositions"].append(dict(disposition))
        return
    record_pipeline_event(
        state,
        "pipeline_disposition",
        [disposition["claim_id"]],
        disposition.get("disposition", ""),
    )


def record_pipeline_event(
    state: Any,
    operation: str,
    ids: list[str],
    detail: str = "",
) -> None:
    change = getattr(state, "_change", None)
    if callable(change):
        change(operation, ids, detail)
        return

    # Legacy test/dummy state: there is no audit log to mutate.
    # Do not invent a persistence layer for such objects.
    return


def record_pipeline_cycle(state: Any, cycle: Mapping[str, Any]) -> None:
    add_cycle = getattr(state, "add_cycle", None)
    if not callable(add_cycle):
        raise TypeError("State does not expose add_cycle()")
    add_cycle(dict(cycle))
