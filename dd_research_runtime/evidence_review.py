"""Cycle 112: snapshot-bound source fidelity and auditable evidence review.

Snapshots must be independently obtained from the source; supplying the same executor
text as a snapshot does not constitute independent verification.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Callable
import copy
from .retrieval_validation import RetrievalValidation
from .payload_limits import checked_payloads, check_snapshot


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _identity(doc: Any) -> tuple[str, str, str]:
    return (doc.url.strip(), doc.content_location.strip(), doc.passage.strip())


@dataclass(frozen=True)
class EvidenceReview:
    batch_digest: str
    reviewer: str
    decision: str
    rationale: str
    snapshot_digests: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    record_digest: str


@dataclass(frozen=True)
class ContextEvidenceReview(EvidenceReview):
    """A review bound to an explicit renewed-candidate context."""
    candidate_context: str


def review_retrieval(validation: RetrievalValidation, *, snapshots: Mapping[str, Mapping[str, str]],
                     reviewer: str, decision: str, rationale: str, state: Any = None, candidate_context: str = "") -> EvidenceReview:
    """Review a whole batch; exact passage and location must match supplied snapshots.

    snapshots[source_id] = {'text': full_source_text, 'location': exact_locator}.
    A review is a record, not proof of reviewer authentication or source authenticity.
    """
    if not isinstance(candidate_context, str):
        raise ValueError('candidate_context must be a string')
    if validation.status != 'ready_for_review' or not validation.documents:
        raise ValueError('only validated retrieval batches can be reviewed')
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(rationale, str) or not rationale.strip():
        raise ValueError('reviewer and rationale are required')
    if decision not in {'approved', 'rejected'}:
        raise ValueError('decision must be approved or rejected')
    checked_payloads(validation.documents)
    snapshot_total = 0
    snapshot_hashes = []
    seen = set()
    duplicates = []
    for doc in validation.documents:
        doc.validate()
        snapshot = snapshots.get(doc.source_id)
        if not isinstance(snapshot, Mapping):
            raise ValueError(f'missing independent source snapshot: {doc.source_id}')
        full_text, location = snapshot.get('text'), snapshot.get('location')
        if not isinstance(full_text, str) or not isinstance(location, str):
            raise ValueError('snapshot text and location must be strings')
        snapshot_total = check_snapshot(full_text,location,snapshot_total)
        if doc.passage not in full_text or doc.content_location != location:
            raise ValueError(f'passage or exact location not verified: {doc.source_id}')
        snapshot_hashes.append(_digest({'source_id': doc.source_id, 'text': full_text, 'location': location}))
        key = _identity(doc)
        if key in seen:
            duplicates.append(doc.source_id)
        seen.add(key)
        if state is not None:
            for existing in getattr(state, 'evidence', {}).values():
                metadata = existing.get('metadata', {})
                if (metadata.get('url'), existing.get('exact_location'), existing.get('finding')) == key:
                    duplicates.append(doc.source_id)
                    break
    if duplicates and decision == 'approved':
        raise ValueError('duplicate evidence cannot be approved: ' + ', '.join(duplicates))
    batch_digest = _digest([doc.to_evidence_payload() for doc in validation.documents])
    base = dict(batch_digest=batch_digest, reviewer=reviewer.strip(), decision=decision,
                rationale=rationale.strip(), snapshot_digests=tuple(snapshot_hashes),
                duplicate_keys=tuple(duplicates))
    if candidate_context:
        base['candidate_context'] = candidate_context
        return ContextEvidenceReview(**base, record_digest=_digest(base))
    return EvidenceReview(**base, record_digest=_digest(base))


def ingest_with_review(state: Any, validation: RetrievalValidation, review: EvidenceReview, *,
                       authorize: Callable[[str, str], bool] | None = None) -> list[dict[str, Any]]:
    """Fail closed on stale review, duplicates, or missing sources before mutation.

    A review is not authenticated human approval. Callers must enforce identity/access.
    """
    if authorize is None or not callable(authorize) or authorize(review.reviewer, 'evidence_ingest') is not True:
        raise PermissionError('authenticated reviewer authorization required')
    if review.decision != 'approved':
        raise PermissionError('approved review required')
    base = dict(batch_digest=review.batch_digest, reviewer=review.reviewer, decision=review.decision,
                rationale=review.rationale, snapshot_digests=review.snapshot_digests, duplicate_keys=review.duplicate_keys)
    if isinstance(review, ContextEvidenceReview):
        base['candidate_context'] = review.candidate_context
    if review.record_digest != _digest(base):
        raise ValueError('review record integrity mismatch')
    if review.batch_digest != _digest(checked_payloads(validation.documents)):
        raise ValueError('review does not match retrieval batch')
    if review.duplicate_keys:
        raise ValueError('review includes duplicate evidence')
    if validation.status != 'ready_for_review':
        raise ValueError('batch no longer eligible')
    if not hasattr(state, 'evidence') or not hasattr(state, 'sources'):
        raise TypeError('state must expose evidence and sources')
    identities = {(e.get('metadata', {}).get('url'), e.get('exact_location'), e.get('finding'))
                  for e in state.evidence.values()}
    for doc in validation.documents:
        if _identity(doc) in identities or doc.source_id in state.evidence:
            raise ValueError('duplicate evidence already in state')
        if not doc.synthetic and doc.source_id in state.sources:
            raise ValueError('source ID already in state; manual reconciliation required')
        if not doc.synthetic and not doc.independence_cluster:
            raise ValueError('independence_cluster required by state')
    from research_pipeline import retrieve_to_state
    # Stage on an isolated copy. A failure anywhere in the batch leaves the original untouched.
    staged = copy.deepcopy(state)
    results = [retrieve_to_state(staged, doc) for doc in validation.documents]
    if hasattr(staged, '_change'):
        staged._change('evidence_review', [r['evidence_id'] for r in results], review.record_digest)
    if type(state) is not type(staged) or not hasattr(state, '__dict__'):
        raise TypeError('atomic commit requires mutable state object')
    state.__dict__.clear()
    state.__dict__.update(staged.__dict__)
    return results
