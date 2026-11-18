"""One SQLite commit for reviewed evidence, state, receipt and retry record.

The database is authoritative. Call load() after interruption; do not use a separate
mutable ResearchState as a durable mirror. SQLite recovers uncommitted transactions
on reopening. operation_id is a caller-retained idempotency key, not an identity.
"""
import copy
import json
from contextlib import closing
from dataclasses import asdict
from hashlib import sha256

from .evidence_review import ingest_with_review
from .review_ledger import ReviewLedger
from .runtime import ResearchState


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _checksum(value):
    return sha256(value.encode('utf-8')).hexdigest()


class PersistentEvidenceStore:
    """One research state per database, with independent state/ledger revisions.

    Legacy ReviewLedger.append remains usable for review-only receipts. Legacy
    ingest_with_review remains in-memory only; coordinated writes use ingest().
    Authorization callbacks must be side-effect-free and supplied by the host.
    """
    def __init__(self, path):
        if str(path) == ':memory:':
            raise ValueError('persistent database path required')
        self.ledger = ReviewLedger(path)
        with closing(self.ledger._connect()) as db:
            db.execute('CREATE TABLE IF NOT EXISTS research_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, snapshot TEXT NOT NULL, digest TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS ingestion_operations (operation_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, review_digest TEXT NOT NULL UNIQUE REFERENCES receipts(review_digest), result TEXT NOT NULL, result_digest TEXT NOT NULL)')
            from .review_archive import initialize_archive
            initialize_archive(db)
            from .state_journal import initialize_journal
            initialize_journal(db,validate_existing=self._verify_integrity)

    def _connect(self):
        db = self.ledger._connect()
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        return db

    def initialize(self, state):
        """Explicit one-time bootstrap; never replace an existing durable state."""
        if type(state) is not ResearchState:
            raise TypeError('ResearchState required')
        ok, errors = state.validate()
        if not ok:
            raise ValueError(f'invalid research state: {errors}')
        snapshot = _encode(state.snapshot())
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO research_state VALUES (1,0,?,?)', (snapshot, _checksum(snapshot)))
            from .state_journal import bootstrap
            bootstrap(db,snapshot)

    def _load(self, db):
        row = db.execute('SELECT revision,snapshot,digest FROM research_state WHERE id=1').fetchone()
        if row is None:
            raise RuntimeError('initialize durable state first')
        revision, snapshot, digest = row
        if _checksum(snapshot) != digest:
            raise ValueError('state integrity mismatch')
        state = ResearchState()
        state.__dict__ = json.loads(snapshot)
        ok, errors = state.validate()
        if not ok:
            raise ValueError(f'invalid durable state: {errors}')
        return state, revision

    def _verify_integrity(self, db):
        """Reconcile all records in the caller's single database snapshot.

        These checks detect partial corruption; they are not a signed history or
        proof against an attacker able to rewrite the whole database.
        """
        if not self.ledger._verify(db):
            raise ValueError('ledger integrity mismatch')
        state, revision = self._load(db)
        if type(revision) is not int or revision < 0:
            raise ValueError('state revision integrity mismatch')
        receipts = db.execute('SELECT seq,review_digest,decision,entry_hash FROM receipts ORDER BY seq').fetchall()
        by_review = {r[1]: r for r in receipts}
        operations = db.execute('SELECT operation_id,request_digest,review_digest,result,result_digest FROM ingestion_operations').fetchall()
        revisions, used_evidence, ledger_positions = set(), set(), []
        for operation_id, request_digest, review_digest, encoded, digest in operations:
            if _checksum(encoded) != digest:
                raise ValueError('operation result integrity mismatch')
            try:
                result = json.loads(encoded)
                if (not isinstance(operation_id, str) or not operation_id.strip()
                        or not isinstance(request_digest, str) or len(request_digest) != 64
                        or any(c not in '0123456789abcdef' for c in request_digest)
                        or not isinstance(result, dict) or result.get('operation_id') != operation_id):
                    raise ValueError('invalid operation identity')
                sr, lr = result['state_revision'], result['ledger_revision']
                if type(sr) is not int or sr < 1 or type(lr) is not int or lr < 1 or sr in revisions:
                    raise ValueError('invalid operation revision')
                receipt = by_review.get(review_digest)
                if receipt is None or receipt[0] != lr or receipt[2] != 'approved' or receipt[3] != result['entry_hash']:
                    raise ValueError('operation receipt mismatch')
                evidence = result['evidence']
                if not isinstance(evidence, list) or not evidence:
                    raise ValueError('missing operation evidence')
                for item in evidence:
                    if not isinstance(item, dict):
                        raise ValueError('invalid operation evidence')
                    eid = item['evidence_id']
                    if not isinstance(eid, str) or eid in used_evidence or state.evidence.get(eid) != item:
                        raise ValueError('operation evidence mismatch')
                    if not item.get('synthetic'):
                        source = state.sources.get(item['source_id'])
                        metadata = item['metadata']
                        if (not source or source.get('provenance') != item.get('provenance')
                                or source.get('independence_cluster') != item.get('independence_cluster')
                                or any(source.get(k) != metadata.get(k) for k in ('title','publisher','url','retrieved_at','published_at'))):
                            raise ValueError('operation source mismatch')
                    used_evidence.add(eid)
                revisions.add(sr)
                ledger_positions.append((sr, lr))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('operation history integrity mismatch: '+str(exc)) from exc
        from .state_journal import present
        if not present(db) and (len(operations) != revision or any(value != index for index,value in enumerate(sorted(revisions),1))):
            raise ValueError('operation history revision integrity mismatch')
        positions = [lr for _, lr in sorted(ledger_positions)]
        if positions != sorted(set(positions)):
            raise ValueError('operation ledger ordering integrity mismatch')
        from .review_archive import verify_archive
        verify_archive(db,operations)
        from .state_journal import verify
        verify(db,state,revision,operations)
        return state, revision, len(receipts), len(operations)

    def verify_integrity(self):
        """Return counts after complete reconciliation; raise on inconsistency.

        Review-only receipts and bootstrap evidence need not have ingestion
        operation records. A single read transaction prevents torn reads during
        concurrent commits. No repair or authorization inference is performed.
        """
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            _, revision, receipts, operations = self._verify_integrity(db)
            return dict(state_revision=revision, ledger_revision=receipts, operations=operations)

    def load(self):
        """Recover an isolated state only after complete history reconciliation."""
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            state, revision, _, _ = self._verify_integrity(db)
            return state, revision

    def load_with_revisions(self):
        """Return detached state plus state/ledger revisions from one snapshot."""
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            state, revision, receipts, _ = self._verify_integrity(db)
            return state, revision, receipts

    def ingest(self, validation, review, *, operation_id, expected_state_revision,
               expected_ledger_revision, authorize=None, _fault=None, _pending_id=None, source_snapshots=None):
        """Return committed result or the same result for an identical retry.

        A retry still requires current host authorization. Revisions are checked
        for new operations; an identical committed retry returns its original
        revisions even when later commits exist. _fault is a test-only callback.
        """
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError('operation_id required')
        for revision in (expected_state_revision, expected_ledger_revision):
            if type(revision) is not int or revision < 0:
                raise ValueError('expected revisions must be nonnegative integers')
        if not callable(authorize) or authorize(review.reviewer, 'evidence_ingest') is not True:
            raise PermissionError('authenticated reviewer authorization required')
        from .payload_limits import checked_payloads
        checked_payloads(validation.documents)
        # Freeze caller inputs so the transaction cannot race mutable metadata.
        validation, review, source_snapshots = copy.deepcopy((validation, review, source_snapshots))
        request_payload = dict(review=asdict(review), status=validation.status,
                               documents=checked_payloads(validation.documents))
        if source_snapshots is not None:
            from .source_snapshots import verify_source_snapshots
            request_payload['source_snapshots'] = verify_source_snapshots(request_payload['documents'],request_payload['review'],source_snapshots)
        request = _checksum(_encode(request_payload))
        def checkpoint(name):
            if _fault is not None:
                _fault(name)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                state, revision, _, _ = self._verify_integrity(db)
                collision=db.execute("SELECT kind FROM state_mutations WHERE operation_id=?",(operation_id,)).fetchone()
                if collision and collision[0] != 'ingestion':raise ValueError('operation_id already used for analysis')
                if _pending_id is not None:
                    from .pending_retrieval import _check_pending
                    _check_pending(db, _pending_id, validation, expected_state_revision,
                                   expected_ledger_revision, operation_id, review)
                prior = db.execute('SELECT request_digest,result,result_digest FROM ingestion_operations WHERE operation_id=?', (operation_id,)).fetchone()
                if prior:
                    if prior[0] != request:
                        raise ValueError('operation_id reused for different request')
                    if _checksum(prior[1]) != prior[2]:
                        raise ValueError('operation result integrity mismatch')
                    if _pending_id is not None:
                        from .pending_retrieval import _finish_pending
                        _finish_pending(db, _pending_id, operation_id)
                    db.execute('COMMIT')
                    return json.loads(prior[1])
                if revision != expected_state_revision:
                    raise RuntimeError('stale state revision')
                # All existing source, review, duplicate and synthetic checks apply.
                from . import state_journal
                before_snapshot=_encode(state.snapshot());start=len(state.change_log);timestamp=state_journal.now()
                evidence = ingest_with_review(state, validation, review, authorize=authorize)
                state_journal.normalize_changes(state,start,timestamp)
                checkpoint('after_staging')
                receipt = self.ledger._append(db, review, expected_revision=expected_ledger_revision)
                checkpoint('after_receipt')
                snapshot = _encode(state.snapshot())
                db.execute('UPDATE research_state SET revision=?,snapshot=?,digest=? WHERE id=1',
                           (revision+1, snapshot, _checksum(snapshot)))
                checkpoint('after_state')
                result = dict(operation_id=operation_id, state_revision=revision+1,
                              ledger_revision=receipt['revision'], entry_hash=receipt['entry_hash'], evidence=evidence)
                encoded = _encode(result)
                db.execute('INSERT INTO ingestion_operations VALUES (?,?,?,?,?)',
                           (operation_id, request, review.record_digest, encoded, _checksum(encoded)))
                from .review_archive import retain
                retain(db,operation_id,request_payload)
                checkpoint('after_review_archive')
                if _pending_id is not None:
                    from .pending_retrieval import _finish_pending
                    _finish_pending(db, _pending_id, operation_id)
                state_journal.append(db,revision=revision+1,operation_id=operation_id,kind='ingestion',
                    request=dict(ingestion_request_digest=request,review_digest=review.record_digest),result=result,
                    before_snapshot=before_snapshot,state=state,timestamp=timestamp)
                checkpoint('after_journal')
                self._verify_integrity(db)
                checkpoint('before_commit')
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise
        checkpoint('after_commit')
        return result

    def review_coverage(self):
        """Report legacy versus fully retained approved ingestion reviews."""
        from .review_archive import verify_archive
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            self._verify_integrity(db)
            rows=db.execute('SELECT operation_id,request_digest,review_digest,result,result_digest FROM ingestion_operations').fetchall()
            return verify_archive(db,rows)

    def load_review(self, operation_id):
        """Return an isolated retained request/review; never invent legacy content."""
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            self._verify_integrity(db)
            if not db.execute('SELECT 1 FROM ingestion_operations WHERE operation_id=?',(operation_id,)).fetchone():
                raise KeyError('unknown ingestion operation: '+operation_id)
            row=db.execute('SELECT payload FROM ingestion_review_archive WHERE operation_id=?',(operation_id,)).fetchone()
            if row is None:
                raise LookupError('legacy review payload was not retained')
            return json.loads(row[0])

    def load_source_snapshots(self, operation_id):
        """Return isolated retained text/locator data; never invent missing content."""
        data=self.load_review(operation_id)
        if 'source_snapshots' not in data:
            raise LookupError('source snapshots were not retained for this operation')
        return data['source_snapshots']

    def snapshot_coverage(self):
        """Report retained content separately from review hashes and legacy gaps."""
        from .review_archive import verify_archive
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            self._verify_integrity(db)
            operations=db.execute('SELECT operation_id,request_digest,review_digest,result,result_digest FROM ingestion_operations').fetchall()
            coverage=verify_archive(db,operations)
            retained=without=total=0
            for encoded, in db.execute('SELECT payload FROM ingestion_review_archive'):
                request=json.loads(encoded)
                if 'source_snapshots' in request:
                    retained+=1
                    total+=len(request['source_snapshots'])
                else:
                    without+=1
            return dict(legacy_operations=coverage['legacy_operations'],retained_snapshot_sets=retained,
                        reviews_without_snapshots=without,snapshots=total)

    def apply_analysis(self, commands, *, operation_id, actor, rationale,
                       expected_state_revision, authorize=None, _fault=None):
        """Atomically persist typed advisory analysis, never source/gate changes."""
        from . import state_journal
        from .analysis_transactions import apply_commands, _text
        _text(operation_id,'operation_id');_text(actor,'actor');_text(rationale,'rationale')
        if operation_id.startswith('pending/'):raise ValueError('pending/ operation IDs are reserved')
        if type(expected_state_revision) is not int or expected_state_revision < 0:raise ValueError('expected_state_revision must be a nonnegative integer')
        if not callable(authorize) or authorize(actor,'analysis_write') is not True:raise PermissionError('authenticated analysis authorization required')
        commands=copy.deepcopy(commands)
        if not isinstance(commands,list) or not 1 <= len(commands) <= 100:raise ValueError('analysis requires 1 to 100 commands')
        request=dict(actor=actor,rationale=rationale,commands=commands)
        encoded=_encode(request)
        if len(encoded.encode('utf-8')) > 2*1024*1024:raise ValueError('analysis request exceeds byte limit')
        digest=_checksum(encoded)
        def checkpoint(name):
            if _fault is not None:_fault(name)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                state,revision,_,_=self._verify_integrity(db)
                if db.execute('SELECT 1 FROM ingestion_operations WHERE operation_id=?',(operation_id,)).fetchone():raise ValueError('operation_id already used for ingestion')
                prior=db.execute('SELECT kind,request_digest,result FROM state_mutations WHERE operation_id=?',(operation_id,)).fetchone()
                if prior:
                    if prior[0]!='analysis' or prior[1]!=digest:raise ValueError('operation_id reused for different analysis request')
                    db.execute('COMMIT');return json.loads(prior[2])
                if revision != expected_state_revision:raise RuntimeError('stale state revision')
                before=_encode(state.snapshot());timestamp=state_journal.now()
                changed=apply_commands(state,commands,actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
                checkpoint('after_staging')
                snapshot=_encode(state.snapshot())
                db.execute('UPDATE research_state SET revision=?,snapshot=?,digest=? WHERE id=1',(revision+1,snapshot,_checksum(snapshot)))
                checkpoint('after_state')
                result=dict(operation_id=operation_id,state_revision=revision+1,kind='analysis',actor=actor,changed_ids=changed)
                state_journal.append(db,revision=revision+1,operation_id=operation_id,kind='analysis',request=request,result=result,before_snapshot=before,state=state,timestamp=timestamp)
                checkpoint('after_journal')
                self._verify_integrity(db);checkpoint('before_commit')
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:db.execute('ROLLBACK')
                raise
        checkpoint('after_commit');return result

    def apply_workflow(self, command, *, operation_id, actor, rationale,
                       expected_state_revision, authorize=None, _fault=None):
        """Atomically persist bounded workflow changes and draft reports."""
        from . import state_journal
        from .analysis_transactions import _text
        from .workflow import apply_workflow
        _text(operation_id,'operation_id');_text(actor,'actor');_text(rationale,'rationale')
        if operation_id.startswith('pending/'):raise ValueError('pending/ operation IDs are reserved')
        if type(expected_state_revision) is not int or expected_state_revision < 0:raise ValueError('expected_state_revision must be a nonnegative integer')
        if not callable(authorize) or authorize(actor,'workflow_write') is not True:raise PermissionError('authenticated workflow authorization required')
        command=copy.deepcopy(command)
        if not isinstance(command,dict):raise ValueError('workflow command must be an object')
        request=dict(actor=actor,rationale=rationale,command=command)
        encoded=_encode(request)
        if len(encoded.encode('utf-8')) > 2*1024*1024:raise ValueError('workflow request exceeds byte limit')
        digest=_checksum(encoded)
        def checkpoint(name):
            if _fault is not None:_fault(name)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                state,revision,_,_=self._verify_integrity(db)
                if db.execute('SELECT 1 FROM ingestion_operations WHERE operation_id=?',(operation_id,)).fetchone():raise ValueError('operation_id already used for ingestion')
                prior=db.execute('SELECT kind,request_digest,result FROM state_mutations WHERE operation_id=?',(operation_id,)).fetchone()
                if prior:
                    if prior[0]!='workflow' or prior[1]!=digest:raise ValueError('operation_id reused for different workflow request')
                    db.execute('COMMIT');return json.loads(prior[2])
                if revision != expected_state_revision:raise RuntimeError('stale state revision')
                before=_encode(state.snapshot());timestamp=state_journal.now()
                changed=apply_workflow(state,command,actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
                checkpoint('after_staging')
                snapshot=_encode(state.snapshot())
                db.execute('UPDATE research_state SET revision=?,snapshot=?,digest=? WHERE id=1',(revision+1,snapshot,_checksum(snapshot)))
                checkpoint('after_state')
                result=dict(operation_id=operation_id,state_revision=revision+1,kind='workflow',actor=actor,changed_ids=changed)
                state_journal.append(db,revision=revision+1,operation_id=operation_id,kind='workflow',request=request,result=result,before_snapshot=before,state=state,timestamp=timestamp)
                checkpoint('after_journal')
                self._verify_integrity(db);checkpoint('before_commit')
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:db.execute('ROLLBACK')
                raise
        checkpoint('after_commit');return result

    def apply_acceptance(self, command, *, operation_id, actor, rationale,
                       expected_state_revision, authorize=None, _fault=None):
        """Atomically persist host/fixture acceptance decisions for exact saved reports."""
        from . import state_journal
        from .analysis_transactions import _text
        from .acceptance import apply_acceptance
        _text(operation_id,'operation_id');_text(actor,'actor');_text(rationale,'rationale')
        if operation_id.startswith('pending/'):raise ValueError('pending/ operation IDs are reserved')
        if type(expected_state_revision) is not int or expected_state_revision < 0:raise ValueError('expected_state_revision must be a nonnegative integer')
        if not callable(authorize) or authorize(actor,'acceptance_record') is not True:raise PermissionError('authenticated acceptance authorization required')
        command=copy.deepcopy(command)
        if not isinstance(command,dict):raise ValueError('workflow command must be an object')
        if command.get('decision')=='accept' and command.get('review_mode')=='host' and authorize(actor,'acceptance_confirm_real_sources') is not True:raise PermissionError('real-source human confirmation authorization required')
        request=dict(actor=actor,rationale=rationale,command=command)
        encoded=_encode(request)
        if len(encoded.encode('utf-8')) > 2*1024*1024:raise ValueError('acceptance request exceeds byte limit')
        digest=_checksum(encoded)
        def checkpoint(name):
            if _fault is not None:_fault(name)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                state,revision,_,_=self._verify_integrity(db)
                if db.execute('SELECT 1 FROM ingestion_operations WHERE operation_id=?',(operation_id,)).fetchone():raise ValueError('operation_id already used for ingestion')
                prior=db.execute('SELECT kind,request_digest,result FROM state_mutations WHERE operation_id=?',(operation_id,)).fetchone()
                if prior:
                    if prior[0]!='acceptance' or prior[1]!=digest:raise ValueError('operation_id reused for different acceptance request')
                    db.execute('COMMIT');return json.loads(prior[2])
                if revision != expected_state_revision:raise RuntimeError('stale state revision')
                before=_encode(state.snapshot());timestamp=state_journal.now()
                changed=apply_acceptance(state,command,db=db,actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
                checkpoint('after_staging')
                snapshot=_encode(state.snapshot())
                db.execute('UPDATE research_state SET revision=?,snapshot=?,digest=? WHERE id=1',(revision+1,snapshot,_checksum(snapshot)))
                checkpoint('after_state')
                result=dict(operation_id=operation_id,state_revision=revision+1,kind='acceptance',actor=actor,changed_ids=changed)
                state_journal.append(db,revision=revision+1,operation_id=operation_id,kind='acceptance',request=request,result=result,before_snapshot=before,state=state,timestamp=timestamp)
                checkpoint('after_journal')
                self._verify_integrity(db);checkpoint('before_commit')
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:db.execute('ROLLBACK')
                raise
        checkpoint('after_commit');return result

    def apply_gate(self, command, *, operation_id, actor, rationale,
                       expected_state_revision, authorize=None, _fault=None):
        """Atomically persist typed gate proposals and decisions."""
        if not isinstance(command,dict):raise ValueError('gate command must be an object')
        command=copy.deepcopy(command)
        from . import state_journal
        from .analysis_transactions import _text
        from .gate_transactions import apply_gate
        _text(operation_id,'operation_id');_text(actor,'actor');_text(rationale,'rationale')
        if operation_id.startswith('pending/'):raise ValueError('pending/ operation IDs are reserved')
        if type(expected_state_revision) is not int or expected_state_revision < 0:raise ValueError('expected_state_revision must be a nonnegative integer')
        if not callable(authorize) or authorize(actor, {'propose':'gate_propose','decide':'gate_decide','execute':'gate_execute'}.get(command.get('type'),'gate_invalid')) is not True:raise PermissionError('authenticated gate authorization required')
        request=dict(actor=actor,rationale=rationale,command=command)
        encoded=_encode(request)
        if len(encoded.encode('utf-8')) > 2*1024*1024:raise ValueError('gate request exceeds byte limit')
        digest=_checksum(encoded)
        def checkpoint(name):
            if _fault is not None:_fault(name)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                state,revision,_,_=self._verify_integrity(db)
                if db.execute('SELECT 1 FROM ingestion_operations WHERE operation_id=?',(operation_id,)).fetchone():raise ValueError('operation_id already used for ingestion')
                prior=db.execute('SELECT kind,request_digest,result FROM state_mutations WHERE operation_id=?',(operation_id,)).fetchone()
                if prior:
                    if prior[0]!='gate' or prior[1]!=digest:raise ValueError('operation_id reused for different gate request')
                    db.execute('COMMIT');return json.loads(prior[2])
                if revision != expected_state_revision:raise RuntimeError('stale state revision')
                before=_encode(state.snapshot());timestamp=state_journal.now()
                changed=apply_gate(state,command,actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
                checkpoint('after_staging')
                snapshot=_encode(state.snapshot())
                db.execute('UPDATE research_state SET revision=?,snapshot=?,digest=? WHERE id=1',(revision+1,snapshot,_checksum(snapshot)))
                checkpoint('after_state')
                result=dict(operation_id=operation_id,state_revision=revision+1,kind='gate',actor=actor,changed_ids=changed)
                state_journal.append(db,revision=revision+1,operation_id=operation_id,kind='gate',request=request,result=result,before_snapshot=before,state=state,timestamp=timestamp)
                checkpoint('after_journal')
                self._verify_integrity(db);checkpoint('before_commit')
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:db.execute('ROLLBACK')
                raise
        checkpoint('after_commit');return result

    def mutation_coverage(self):
        from .state_journal import verify
        with closing(self._connect()) as db, db:
            db.execute('BEGIN')
            state,revision,_,_=self._verify_integrity(db)
            rows=db.execute('SELECT operation_id,request_digest,review_digest,result,result_digest FROM ingestion_operations').fetchall()
            return verify(db,state,revision,rows)

    def load_analysis_operation(self, operation_id):
        with closing(self._connect()) as db, db:
            db.execute('BEGIN');self._verify_integrity(db)
            row=db.execute("SELECT request,result,timestamp,entry_hash FROM state_mutations WHERE operation_id=? AND kind='analysis'",(operation_id,)).fetchone()
            if not row:raise KeyError('unknown analysis operation')
            return dict(request=json.loads(row[0]),result=json.loads(row[1]),timestamp=row[2],entry_hash=row[3])

    def load_gate_operation(self, operation_id):
        """Read a verified proposal, decision or local consumption audit record."""
        with closing(self._connect()) as db, db:
            db.execute('BEGIN');self._verify_integrity(db)
            row=db.execute("SELECT request,result,timestamp,entry_hash FROM state_mutations WHERE operation_id=? AND kind='gate'",(operation_id,)).fetchone()
            if not row:raise KeyError('unknown gate operation')
            return dict(request=json.loads(row[0]),result=json.loads(row[1]),timestamp=row[2],entry_hash=row[3])

    def load_workflow_operation(self, operation_id):
        """Read a verified workflow or draft-report audit record."""
        with closing(self._connect()) as db, db:
            db.execute('BEGIN');self._verify_integrity(db)
            row=db.execute("SELECT request,result,timestamp,entry_hash FROM state_mutations WHERE operation_id=? AND kind='workflow'",(operation_id,)).fetchone()
            if not row:raise KeyError('unknown workflow operation')
            return dict(request=json.loads(row[0]),result=json.loads(row[1]),timestamp=row[2],entry_hash=row[3])

    def acceptance_status(self, report_id):
        from .acceptance import case_status
        with closing(self._connect()) as db, db:
            db.execute('BEGIN');state,_,_,_=self._verify_integrity(db)
            return case_status(state,report_id,db=db)

    def load_acceptance_operation(self, operation_id):
        with closing(self._connect()) as db, db:
            db.execute('BEGIN');self._verify_integrity(db)
            row=db.execute("SELECT request,result,timestamp,entry_hash FROM state_mutations WHERE operation_id=? AND kind='acceptance'",(operation_id,)).fetchone()
            if not row:raise KeyError('unknown acceptance operation')
            return dict(request=json.loads(row[0]),result=json.loads(row[1]),timestamp=row[2],entry_hash=row[3])
