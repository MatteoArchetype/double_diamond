"""Validate untrusted retrieval executor output; never auto-promote to evidence."""
from dataclasses import dataclass
from typing import Any, Mapping
from retrieval_adapter import RetrievedDocument
from . import payload_limits

@dataclass(frozen=True)
class RetrievalValidation:
    status: str
    documents: tuple[RetrievedDocument, ...]
    errors: tuple[str, ...]

def validate_retrieval_output(action: str, output: Any) -> RetrievalValidation:
    """Accept only successful retrieve actions with complete, explicit source records.

    This is a structural gate, NOT verification of the truth or source fidelity.
    The caller must explicitly approve ingestion after checking source content.
    """
    if action != "retrieve":
        return RetrievalValidation("not_retrieval", (), ("only retrieve output may be validated",))
    if not isinstance(output, Mapping) or output.get("status") != "completed":
        return RetrievalValidation("rejected", (), ("retrieval execution was not completed",))
    raw = output.get("documents")
    if not isinstance(raw, list) or not raw:
        return RetrievalValidation("rejected", (), ("nonempty documents list required",))
    if len(raw) > payload_limits.MAX_DOCUMENTS:
        return RetrievalValidation('rejected',(),('retrieval document count exceeds limit',))
    documents, errors = [], []
    for i, item in enumerate(raw):
        try:
            if not isinstance(item, Mapping):
                raise TypeError("document must be a mapping")
            doc = RetrievedDocument(**dict(item))
            doc.validate()
            documents.append(doc)
        except (TypeError, ValueError) as exc:
            errors.append(f"documents[{i}]: {exc}")
    if errors:
        return RetrievalValidation("rejected", (), tuple(errors))
    try:
        payload_limits.checked_payloads(documents)
    except (TypeError,ValueError) as exc:
        return RetrievalValidation('rejected',(),(str(exc),))
    ids = [doc.source_id for doc in documents]
    if len(ids) != len(set(ids)):
        return RetrievalValidation("rejected", (), ("duplicate source IDs",))
    return RetrievalValidation("ready_for_review", tuple(documents), ())

def validate_execution_retrieval(execution: Any) -> RetrievalValidation:
    return validate_retrieval_output(execution.action, execution.output)

def ingest_reviewed_retrieval(state: Any, validation: RetrievalValidation, *, approved: bool) -> list[dict[str, Any]]:
    """Disabled legacy boolean approval path. Use authenticated review ingestion."""
    raise PermissionError("legacy boolean approval disabled; use ingest_with_review with authorization")
