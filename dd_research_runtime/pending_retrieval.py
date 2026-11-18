"""Durable review handoff; external retrieval is never executed by this queue."""
import copy
import json
from contextlib import closing
from dataclasses import asdict, dataclass, replace

from .persistent_ingestion import _encode, _checksum
from .persistent_controller import PersistentControllerStep
from .retrieval_validation import RetrievalValidation, validate_execution_retrieval, validate_retrieval_output
from .evidence_review import _digest


@dataclass(frozen=True)
class SavedRetrieval:
    candidate_id: str
    status: str
    state_revision: int
    ledger_revision: int
    validation: RetrievalValidation
    operation_id: str | None
    termination: dict | None = None
    review_context: str = ""
    successor_id: str | None = None
    renewal: dict | None = None


def _operation_id(candidate_id):
    return 'pending/'+candidate_id


def _decode(row):
    cid, encoded, digest, status, operation_id = row
    if _checksum(encoded) != digest:
        raise ValueError('pending candidate integrity mismatch')
    try:
        data = json.loads(encoded)
        if not isinstance(data, dict) or data['candidate_id'] != cid:
            raise ValueError('candidate ID mismatch')
        sr, lr = data['state_revision'], data['ledger_revision']
        if any(type(r) is not int or r < 0 for r in (sr, lr)):
            raise ValueError('invalid candidate revisions')
        validation = validate_retrieval_output('retrieve', data['output'])
        if validation.status != 'ready_for_review':
            raise ValueError('candidate not reviewable')
        if status not in {'pending', 'committed'} or (status == 'pending' and operation_id is not None) or (status == 'committed' and operation_id != _operation_id(cid)):
            raise ValueError('invalid candidate lifecycle')
        return SavedRetrieval(cid, status, sr, lr, validation, operation_id)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('pending candidate integrity mismatch: '+str(exc)) from exc


def _read_pending(db, candidate_id):
    row = db.execute('SELECT candidate_id,payload,digest,status,operation_id FROM pending_retrievals WHERE candidate_id=?', (candidate_id,)).fetchone()
    if row is None:
        raise KeyError('unknown pending candidate: '+candidate_id)
    candidate = _decode(row)
    if candidate.status == 'pending' and db.execute('SELECT 1 FROM ingestion_operations WHERE operation_id=?', (_operation_id(candidate_id),)).fetchone():
        raise ValueError('pending lifecycle integrity mismatch')
    if candidate.status == 'committed':
        linked = db.execute('SELECT o.result,o.result_digest,r.batch_digest FROM ingestion_operations o JOIN receipts r ON r.review_digest=o.review_digest WHERE o.operation_id=?', (candidate.operation_id,)).fetchone()
        if linked is None or _checksum(linked[0]) != linked[1]:
            raise ValueError('pending operation integrity mismatch')
        result = json.loads(linked[0])
        if (result.get('state_revision') != candidate.state_revision+1
                or result.get('ledger_revision') != candidate.ledger_revision+1
                or linked[2] != _digest([d.to_evidence_payload() for d in candidate.validation.documents])):
            raise ValueError('pending operation binding integrity mismatch')
    terminal = db.execute('SELECT payload,digest FROM retrieval_terminations WHERE candidate_id=?', (candidate_id,)).fetchone()
    if terminal:
        data = _validate_terminal(db, candidate, row[2], terminal)
        candidate = replace(candidate, status=data['kind'], termination=data)
    from .candidate_renewal import overlay_renewal
    return overlay_renewal(db,candidate)


def _validate_terminal(db, candidate, candidate_digest, terminal):
    encoded, digest = terminal
    if _checksum(encoded) != digest:
        raise ValueError('termination integrity mismatch')
    try:
        data = json.loads(encoded)
        if (candidate.status != 'pending' or data['candidate_id'] != candidate.candidate_id
                or data['candidate_digest'] != candidate_digest
                or data['kind'] not in {'rejected','cancelled'}
                or not isinstance(data['actor'],str) or not data['actor'].strip()
                or not isinstance(data['rationale'],str) or not data['rationale'].strip()):
            raise ValueError('invalid terminal lifecycle')
        if data['kind'] == 'rejected':
            review = data['review']
            base = {k:v for k,v in review.items() if k != 'record_digest'}
            if (review['record_digest'] != _digest(base) or review['decision'] != 'rejected'
                    or review['reviewer'] != data['actor'] or review['rationale'] != data['rationale']
                    or review['batch_digest'] != _digest([d.to_evidence_payload() for d in candidate.validation.documents])):
                raise ValueError('rejection review mismatch')
            receipt = db.execute('SELECT seq,reviewer,decision,rationale,batch_digest,entry_hash FROM receipts WHERE review_digest=?',(review['record_digest'],)).fetchone()
            if receipt != (data['ledger_revision'],data['actor'],'rejected',data['rationale'],review['batch_digest'],data['entry_hash']):
                raise ValueError('rejection receipt mismatch')
        elif any(data[k] is not None for k in ('review','ledger_revision','entry_hash')):
            raise ValueError('cancellation cannot imply a review receipt')
        return data
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('termination integrity mismatch: '+str(exc)) from exc


def _check_pending(db, candidate_id, validation, sr, lr, operation_id, review=None):
    candidate = _read_pending(db, candidate_id)
    if candidate.status in {'rejected','cancelled','superseded'}:
        raise PermissionError('candidate is terminal: '+candidate.status)
    if candidate.review_context and getattr(review,'candidate_context',None) != candidate.review_context:
        raise PermissionError('fresh candidate-bound review required')
    if (operation_id != _operation_id(candidate_id) or candidate.validation != validation
            or candidate.state_revision != sr or candidate.ledger_revision != lr):
        raise ValueError('pending candidate does not match ingestion request')


def _finish_pending(db, candidate_id, operation_id):
    db.execute("UPDATE pending_retrievals SET status='committed',operation_id=? WHERE candidate_id=?", (operation_id,candidate_id))
    _read_pending(db, candidate_id)  # Verify completion binding before COMMIT.


class PendingRetrievalQueue:
    """One explicit immutable candidate ID per successful preparation.

    Save is idempotent for identical content; it never refreshes revisions or
    executes retrieval. Read methods verify all queue records and base history.
    The host provides storage access control; no identity is inferred here.
    """
    def __init__(self, store):
        self.store = store
        with closing(store._connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS pending_retrievals (candidate_id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','committed')), operation_id TEXT UNIQUE REFERENCES ingestion_operations(operation_id))")
            db.execute("CREATE TABLE IF NOT EXISTS retrieval_terminations (candidate_id TEXT PRIMARY KEY REFERENCES pending_retrievals(candidate_id), payload TEXT NOT NULL, digest TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS candidate_renewals (child_id TEXT PRIMARY KEY REFERENCES pending_retrievals(candidate_id), parent_id TEXT NOT NULL UNIQUE REFERENCES pending_retrievals(candidate_id), payload TEXT NOT NULL, digest TEXT NOT NULL)")

    def _verify(self, db):
        self.store._verify_integrity(db)
        if db.execute('SELECT 1 FROM retrieval_terminations t LEFT JOIN pending_retrievals p ON p.candidate_id=t.candidate_id WHERE p.candidate_id IS NULL LIMIT 1').fetchone():
            raise ValueError('orphan termination integrity mismatch')
        from .candidate_renewal import verify_renewals
        verify_renewals(db)
        ids = db.execute('SELECT candidate_id FROM pending_retrievals ORDER BY candidate_id').fetchall()
        return [_read_pending(db, row[0]) for row in ids]

    def save(self, candidate_id, candidate):
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError('candidate_id required')
        if not isinstance(candidate, PersistentControllerStep):
            raise TypeError('PersistentControllerStep required')
        candidate = copy.deepcopy(candidate)
        execution = candidate.step.execution
        if (candidate.status != 'ready_for_review' or candidate.step.status != 'completed'
                or execution is None or execution.status != 'completed' or execution.action != 'retrieve'):
            raise PermissionError('successful retrieval candidate required')
        validation = validate_execution_retrieval(execution)
        if validation.status != 'ready_for_review' or validation != candidate.validation:
            raise ValueError('candidate does not match execution output')
        data = dict(candidate_id=candidate_id, state_revision=candidate.state_revision,
                    ledger_revision=candidate.ledger_revision,
                    output=dict(status='completed', documents=[asdict(d) for d in validation.documents]))
        encoded = _encode(data)
        # Validate before mutation; only normalized document data is stored.
        _decode((candidate_id, encoded, _checksum(encoded), 'pending', None))
        with closing(self.store._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._verify(db)
            prior = db.execute('SELECT payload FROM pending_retrievals WHERE candidate_id=?', (candidate_id,)).fetchone()
            if prior:
                if prior[0] != encoded:
                    raise ValueError('candidate_id reused for different content')
            else:
                db.execute("INSERT INTO pending_retrievals VALUES (?,?,?,'pending',NULL)", (candidate_id,encoded,_checksum(encoded)))
            return _read_pending(db,candidate_id)

    def load(self, candidate_id):
        with closing(self.store._connect()) as db, db:
            db.execute('BEGIN')
            self._verify(db)
            return _read_pending(db,candidate_id)

    def list_pending(self):
        with closing(self.store._connect()) as db, db:
            db.execute('BEGIN')
            return [c for c in self._verify(db) if c.status == 'pending']

    def commit(self, candidate_id, review, *, authorize=None, _fault=None, source_snapshots=None):
        candidate = self.load(candidate_id)
        if candidate.status in {'rejected','cancelled','superseded'}:
            raise PermissionError('candidate is terminal: '+candidate.status)
        return self.store.ingest(candidate.validation, review,
            operation_id=_operation_id(candidate_id),
            expected_state_revision=candidate.state_revision,
            expected_ledger_revision=candidate.ledger_revision,
            authorize=authorize, _pending_id=candidate_id, _fault=_fault, source_snapshots=source_snapshots)

    def reject(self, candidate_id, review, *, expected_ledger_revision, authorize=None, _fault=None):
        """Record authenticated rejection and its ledger receipt in one commit."""
        from .evidence_review import EvidenceReview
        if not isinstance(review, EvidenceReview) or review.decision != 'rejected':
            raise PermissionError('rejected EvidenceReview required')
        review = copy.deepcopy(review)
        base = asdict(review)
        base.pop('record_digest')
        if review.record_digest != _digest(base):
            raise ValueError('review record integrity mismatch')
        if type(expected_ledger_revision) is not int or expected_ledger_revision < 0:
            raise ValueError('expected_ledger_revision must be a nonnegative integer')
        return self._terminate(candidate_id,'rejected',review.reviewer,review.rationale,
                               review,expected_ledger_revision,authorize,_fault)

    def cancel(self, candidate_id, *, actor, rationale, authorize=None, _fault=None):
        """Record host-authorized administrative cancellation, never approval."""
        return self._terminate(candidate_id,'cancelled',actor,rationale,None,None,authorize,_fault)

    def _terminate(self, candidate_id, kind, actor, rationale, review, expected_revision, authorize, fault):
        if not isinstance(actor,str) or not actor.strip() or not isinstance(rationale,str) or not rationale.strip():
            raise ValueError('actor and rationale required')
        permission = 'evidence_review' if kind == 'rejected' else 'evidence_cancel'
        if not callable(authorize) or authorize(actor,permission) is not True:
            raise PermissionError('authenticated terminal-action authorization required')
        def checkpoint(name):
            if fault is not None: fault(name)
        with closing(self.store._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                self._verify(db)
                candidate = _read_pending(db,candidate_id)
                if candidate.status == 'committed':
                    raise PermissionError('committed candidate cannot be terminated')
                if review is not None and candidate.review_context and getattr(review,'candidate_context',None) != candidate.review_context:
                    raise PermissionError('fresh candidate-bound review required')
                if review is not None and review.batch_digest != _digest([d.to_evidence_payload() for d in candidate.validation.documents]):
                    raise ValueError('review does not match saved candidate')
                if candidate.status == 'superseded':
                    raise PermissionError('superseded candidate cannot be terminated')
                if candidate.status in {'rejected','cancelled'}:
                    prior = candidate.termination
                    if (prior['kind'] != kind or prior['actor'] != actor or prior['rationale'] != rationale
                            or prior['review'] != (json.loads(_encode(asdict(review))) if review is not None else None)):
                        raise ValueError('terminal decision conflict')
                    db.execute('COMMIT')
                    return candidate
                receipt = None
                if review is not None:
                    receipt = self.store.ledger._append(db,review,expected_revision=expected_revision)
                checkpoint('after_receipt')
                digest = db.execute('SELECT digest FROM pending_retrievals WHERE candidate_id=?',(candidate_id,)).fetchone()[0]
                data = dict(candidate_id=candidate_id,candidate_digest=digest,kind=kind,actor=actor,
                            rationale=rationale,review=asdict(review) if review is not None else None,
                            ledger_revision=receipt['revision'] if receipt else None,
                            entry_hash=receipt['entry_hash'] if receipt else None)
                encoded = _encode(data)
                db.execute('INSERT INTO retrieval_terminations VALUES (?,?,?)',(candidate_id,encoded,_checksum(encoded)))
                checkpoint('after_terminal')
                result = _read_pending(db,candidate_id)
                checkpoint('before_commit')
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction: db.execute('ROLLBACK')
                raise
        checkpoint('after_commit')
        return result

    def renew(self, parent_id, child_id, *, actor, rationale, expected_state_revision,
              expected_ledger_revision, authorize=None, _fault=None):
        """Supersede a stale pending candidate with a new immutable review handoff."""
        from .candidate_renewal import renew
        return renew(self,parent_id,child_id,actor=actor,rationale=rationale,
                     expected_state_revision=expected_state_revision,
                     expected_ledger_revision=expected_ledger_revision,
                     authorize=authorize,_fault=_fault)

    def review(self, candidate_id, *, snapshots, reviewer, decision, rationale):
        """Create a review from host-supplied independent snapshots and context."""
        from .evidence_review import review_retrieval
        candidate = self.load(candidate_id)
        if candidate.status != 'pending':
            raise PermissionError('only pending candidates can be reviewed')
        return review_retrieval(candidate.validation,snapshots=snapshots,reviewer=reviewer,
            decision=decision,rationale=rationale,candidate_context=candidate.review_context)
