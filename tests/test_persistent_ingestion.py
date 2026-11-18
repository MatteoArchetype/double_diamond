import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
from dd_research_runtime.evidence_review import review_retrieval
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.retrieval_validation import validate_retrieval_output
from dd_research_runtime.runtime import GateRequired, ResearchState


def auth(reviewer, permission):
    return reviewer == 'human' and permission == 'evidence_ingest'


def batch(sid='s1', synthetic=False):
    doc = dict(source_id=sid, title='Title', publisher='Publisher', url='https://example.org/'+sid,
               retrieved_at='2026-10-21', passage='Exact passage '+sid, content_location='p1',
               provenance='synthetic' if synthetic else 'publisher', independence_cluster='publisher', synthetic=synthetic)
    v = validate_retrieval_output('retrieve', {'status':'completed', 'documents':[doc]})
    r = review_retrieval(v, snapshots={sid: {'text':doc['passage'], 'location':'p1'}},
                        reviewer='human', decision='approved', rationale='Checked snapshot')
    return v, r


def ingest(store, sid='s1', **kwargs):
    options = dict(operation_id=sid, expected_state_revision=0, expected_ledger_revision=0, authorize=auth)
    options.update(kwargs)
    return store.ingest(*batch(sid), **options)


@pytest.fixture
def store(tmp_path):
    s = PersistentEvidenceStore(tmp_path/'research.db')
    state = ResearchState(research_id='research')
    state.create_gate('publication', 'publication', 'Publish', 'Review', 'Approve')
    s.initialize(state)
    return s


def test_commit_restart_and_isolated_load(store):
    result = ingest(store)
    reopened = PersistentEvidenceStore(store.ledger.path)
    state, revision = reopened.load()
    assert revision == result['state_revision'] == 1
    assert reopened.ledger.revision() == 1 and reopened.ledger.verify()
    assert state.evidence['s1']['finding'] == 'Exact passage s1'
    assert state.sources['s1']['provenance'] == 'publisher'
    assert state.evidence['s1']['metadata']['url'] == 'https://example.org/s1'
    state.evidence.clear()
    assert 's1' in reopened.load()[0].evidence


@pytest.mark.parametrize('phase', ['after_staging', 'after_receipt', 'after_state', 'before_commit'])
@pytest.mark.parametrize('error', [RuntimeError, KeyboardInterrupt])
def test_failure_is_atomic(store, phase, error):
    before = store.load()[0].snapshot()
    def fail(name):
        if name == phase: raise error('interrupted')
    with pytest.raises(error): ingest(store, _fault=fail)
    assert store.load()[0].snapshot() == before
    assert store.load()[1] == store.ledger.revision() == 0
    with sqlite3.connect(store.ledger.path) as db:
        assert db.execute('SELECT COUNT(*) FROM ingestion_operations').fetchone()[0] == 0
    assert ingest(store)['state_revision'] == 1


def crash_worker(path, phase):
    def crash(name):
        if name == phase: os._exit(73)
    ingest(PersistentEvidenceStore(path), _fault=crash)


@pytest.mark.parametrize('phase', ['after_receipt', 'after_state', 'before_commit', 'after_commit'])
def test_process_death_recovery(store, phase):
    p = multiprocessing.get_context('spawn').Process(target=crash_worker, args=(store.ledger.path, phase))
    p.start(); p.join(15)
    if p.is_alive():
        p.terminate(); p.join(); pytest.fail('crash worker timed out')
    assert p.exitcode == 73
    reopened = PersistentEvidenceStore(store.ledger.path)
    assert reopened.load()[1] == reopened.ledger.revision() == int(phase == 'after_commit')
    assert ingest(reopened)['state_revision'] == reopened.ledger.revision() == 1
    assert len(reopened.load()[0].evidence) == 1


def test_lost_acknowledgement_and_retry_after_later_commit(store):
    def fail(phase):
        if phase == 'after_commit': raise RuntimeError('lost acknowledgement')
    with pytest.raises(RuntimeError, match='lost acknowledgement'): ingest(store, _fault=fail)
    first = ingest(store)
    ingest(store, 's2', expected_state_revision=1, expected_ledger_revision=1)
    assert ingest(store) == first
    assert store.load()[1] == store.ledger.revision() == 2


def test_operation_key_collision(store):
    ingest(store)
    with pytest.raises(ValueError, match='different request'): ingest(store, 's2', operation_id='s1')
    assert store.load()[1] == store.ledger.revision() == 1


@pytest.mark.parametrize('kind', ['missing_auth', 'rejected', 'tampered', 'changed_batch', 'duplicate'])
def test_fail_closed(store, kind):
    v, r = batch()
    options = dict(operation_id='op', expected_state_revision=0, expected_ledger_revision=0, authorize=auth)
    if kind == 'missing_auth': options['authorize'] = None
    elif kind == 'rejected': r = replace(r, decision='rejected')
    elif kind == 'tampered': r = replace(r, rationale='altered')
    elif kind == 'changed_batch': v = batch('s2')[0]
    elif kind == 'duplicate':
        ingest(store)
        options.update(expected_state_revision=1, expected_ledger_revision=1)
    before = store.load()[0].snapshot()
    with pytest.raises((ValueError, PermissionError)): store.ingest(v, r, **options)
    assert store.load()[0].snapshot() == before
    assert store.ledger.revision() == (1 if kind == 'duplicate' else 0)


def test_retry_requires_current_authorization(store):
    ingest(store)
    with pytest.raises(PermissionError): ingest(store, authorize=lambda *_: False)


def test_state_and_ledger_revisions_are_independent(store):
    store.ledger.append(batch('other')[1], expected_revision=0)
    with pytest.raises(RuntimeError, match='stale ledger'): ingest(store)
    assert not store.load()[0].evidence and store.load()[1] == 0
    ingest(store, expected_ledger_revision=1)
    with pytest.raises(RuntimeError, match='stale state'): ingest(store, 's2', expected_ledger_revision=2)
    assert store.load()[1] == 1 and store.ledger.revision() == 2


@pytest.mark.parametrize('retry', [False, True])
def test_concurrent_connections(store, retry):
    def run(i):
        try: return ingest(PersistentEvidenceStore(store.ledger.path), 's1' if retry else 's'+str(i))
        except RuntimeError as exc: return str(exc)
    with ThreadPoolExecutor(max_workers=6) as pool: results = list(pool.map(run, range(6)))
    successes = [r for r in results if isinstance(r, dict)]
    assert len(successes) == (6 if retry else 1)
    assert all(r == successes[0] for r in successes)
    assert store.load()[1] == store.ledger.revision() == 1
    assert len(store.load()[0].evidence) == 1 and store.ledger.verify()


def race_worker(path, sid, ready, go, output):
    s = PersistentEvidenceStore(path)
    ready.put(True)
    if not go.wait(10): output.put('timeout'); return
    try:
        ingest(s, sid); output.put('committed')
    except RuntimeError as exc: output.put(str(exc))


def test_concurrent_processes(store):
    ctx = multiprocessing.get_context('spawn')
    ready, output, go = ctx.Queue(), ctx.Queue(), ctx.Event()
    workers = [ctx.Process(target=race_worker, args=(store.ledger.path, 's'+str(i), ready, go, output)) for i in range(3)]
    try:
        for p in workers: p.start()
        for _ in workers: assert ready.get(timeout=15)
        go.set()
        results = [output.get(timeout=15) for _ in workers]
        assert results.count('committed') == 1 and results.count('stale state revision') == 2
    finally:
        for p in workers:
            p.join(5)
            if p.is_alive(): p.terminate(); p.join()
        ready.close(); output.close()
    assert store.load()[1] == store.ledger.revision() == 1


def test_synthetic_and_human_gate_preserved(store):
    store.ingest(*batch(synthetic=True), operation_id='synthetic', expected_state_revision=0, expected_ledger_revision=0, authorize=auth)
    state, _ = store.load()
    assert state.evidence['s1']['synthetic'] is True and state.evidence['s1']['provenance'] == 'synthetic'
    assert 's1' not in state.sources
    assert state.human_gates['publication']['status'] == 'pending_review'
    with pytest.raises(GateRequired): state.execute_gated('publication', 'publication')


def test_bootstrap_and_serialization_failure(store):
    with pytest.raises(sqlite3.IntegrityError): store.initialize(ResearchState())
    v, r = batch()
    v.documents[0].metadata['bad'] = object()
    with pytest.raises(TypeError):
        store.ingest(v, r, operation_id='bad', expected_state_revision=0, expected_ledger_revision=0, authorize=auth)
    assert store.load()[1] == store.ledger.revision() == 0


@pytest.mark.parametrize('table,column', [('research_state','snapshot'), ('receipts','rationale'), ('ingestion_operations','result')])
def test_integrity_fail_closed(store, table, column):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db: db.execute(f"UPDATE {table} SET {column}='corrupted'")
    with pytest.raises(ValueError, match='integrity'): ingest(store)


@pytest.mark.parametrize('revision', [True, -1, '0'])
def test_invalid_revisions(store, revision):
    with pytest.raises(ValueError): ingest(store, expected_state_revision=revision)


def test_uninitialized_and_memory_database(tmp_path):
    with pytest.raises(ValueError): PersistentEvidenceStore(':memory:')
    s = PersistentEvidenceStore(tmp_path/'empty.db')
    with pytest.raises(RuntimeError, match='initialize'): s.load()


def test_later_document_failure_rolls_back_whole_batch(store, monkeypatch):
    import research_pipeline
    first, _ = batch('s1')
    second, _ = batch('s2')
    from dataclasses import replace
    v = replace(first, documents=first.documents + second.documents)
    r = review_retrieval(v, snapshots={sid: {'text':'Exact passage '+sid, 'location':'p1'} for sid in ('s1', 's2')},
                        reviewer='human', decision='approved', rationale='Checked both snapshots')
    original = research_pipeline.retrieve_to_state
    def fail_second(state, doc):
        if doc.source_id == 's2': raise RuntimeError('second document failed')
        return original(state, doc)
    monkeypatch.setattr(research_pipeline, 'retrieve_to_state', fail_second)
    before = store.load()[0].snapshot()
    with pytest.raises(RuntimeError, match='second document'):
        store.ingest(v, r, operation_id='batch', expected_state_revision=0, expected_ledger_revision=0, authorize=auth)
    assert store.load()[0].snapshot() == before
    assert store.load()[1] == store.ledger.revision() == 0


def test_receipt_collision_rolls_back_staged_state(store):
    store.ledger.append(batch()[1], expected_revision=0)
    with pytest.raises(sqlite3.IntegrityError): ingest(store, expected_ledger_revision=1)
    assert store.load()[1] == 0 and not store.load()[0].evidence
    assert store.ledger.revision() == 1
