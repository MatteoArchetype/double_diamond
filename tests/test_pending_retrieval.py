import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from test_persistent_ingestion import store, auth, batch, ingest
from test_persistent_controller import prepare, output
from dd_research_runtime.pending_retrieval import PendingRetrievalQueue
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore, _checksum, _encode
from dd_research_runtime.evidence_review import review_retrieval
from dd_research_runtime.runtime import GateRequired


def review_saved(candidate, decision='approved'):
    return review_retrieval(candidate.validation,
        snapshots={d.source_id:dict(text=d.passage,location=d.content_location) for d in candidate.validation.documents},
        reviewer='human',decision=decision,rationale='Checked independent snapshot fixture')


@pytest.fixture
def queue(store):
    q = PendingRetrievalQueue(store)
    q.save('candidate',prepare(store))
    return q


def test_save_reopen_review_commit(queue):
    path = queue.store.ledger.path
    q = PendingRetrievalQueue(PersistentEvidenceStore(path))
    candidate = q.load('candidate')
    assert candidate.status == 'pending' and candidate.operation_id is None
    assert len(q.list_pending()) == 1
    assert q.store.load()[1] == q.store.ledger.revision() == 0
    result = q.commit('candidate',review_saved(candidate),authorize=auth)
    assert result['operation_id'] == 'pending/candidate'
    assert q.load('candidate').status == 'committed' and not q.list_pending()
    assert q.store.load()[1] == q.store.ledger.revision() == 1
    assert q.commit('candidate',review_saved(candidate),authorize=auth) == result
    state = q.store.load()[0]
    assert state.human_gates['publication']['status'] == 'pending_review'
    with pytest.raises(GateRequired): state.execute_gated('publication','publication')


def test_save_idempotent_and_conflict(queue):
    candidate = prepare(queue.store)
    assert queue.save('candidate',candidate) == queue.load('candidate')
    other = prepare(queue.store,executor=lambda **kw:output('s2'))
    with pytest.raises(ValueError,match='reused'): queue.save('candidate',other)
    assert len(queue.list_pending()) == 1
    queue.commit('candidate',review_saved(queue.load('candidate')),authorize=auth)
    assert queue.save('candidate',candidate).status == 'committed'


@pytest.mark.parametrize('phase',['after_staging','after_receipt','after_state','before_commit'])
@pytest.mark.parametrize('error',[RuntimeError,KeyboardInterrupt])
def test_completion_rolls_back_with_evidence(queue,phase,error):
    r = review_saved(queue.load('candidate'))
    def fail(name):
        if name == phase: raise error('interrupted')
    with pytest.raises(error): queue.commit('candidate',r,authorize=auth,_fault=fail)
    assert queue.load('candidate').status == 'pending'
    assert queue.store.load()[1] == queue.store.ledger.revision() == 0
    assert queue.commit('candidate',r,authorize=auth)['state_revision'] == 1


def crash_commit(path,phase):
    q = PendingRetrievalQueue(PersistentEvidenceStore(path))
    def crash(name):
        if name == phase: os._exit(81)
    q.commit('candidate',review_saved(q.load('candidate')),authorize=auth,_fault=crash)


@pytest.mark.parametrize('phase',['after_receipt','after_state','before_commit','after_commit'])
def test_process_crash_recovers_queue_lifecycle(queue,phase):
    path = queue.store.ledger.path
    p = multiprocessing.get_context('spawn').Process(target=crash_commit,args=(path,phase))
    p.start(); p.join(15)
    if p.is_alive(): p.terminate(); p.join(); pytest.fail('crash timeout')
    assert p.exitcode == 81
    q = PendingRetrievalQueue(PersistentEvidenceStore(path))
    c = q.load('candidate')
    assert c.status == ('committed' if phase == 'after_commit' else 'pending')
    assert q.store.load()[1] == q.store.ledger.revision() == int(phase == 'after_commit')
    q.commit('candidate',review_saved(c),authorize=auth)
    assert q.load('candidate').status == 'committed' and q.store.ledger.revision() == 1


def test_concurrent_commit_same_candidate(queue):
    path = queue.store.ledger.path
    r = review_saved(queue.load('candidate'))
    def commit(_):
        return PendingRetrievalQueue(PersistentEvidenceStore(path)).commit('candidate',r,authorize=auth)
    with ThreadPoolExecutor(max_workers=5) as pool: results = list(pool.map(commit,range(5)))
    assert all(x == results[0] for x in results)
    assert queue.store.ledger.revision() == queue.store.load()[1] == 1
    assert queue.load('candidate').status == 'committed'


def test_stale_candidate_stays_pending(queue):
    r = review_saved(queue.load('candidate'))
    ingest(queue.store,'other')
    with pytest.raises(RuntimeError,match='stale state'): queue.commit('candidate',r,authorize=auth)
    assert queue.load('candidate').status == 'pending'
    assert 's1' not in queue.store.load()[0].evidence


def test_stale_ledger_candidate_stays_pending(queue):
    queue.store.ledger.append(batch('other')[1],expected_revision=0)
    with pytest.raises(RuntimeError,match='stale ledger'):
        queue.commit('candidate',review_saved(queue.load('candidate')),authorize=auth)
    assert queue.load('candidate').status == 'pending' and queue.store.load()[1] == 0


@pytest.mark.parametrize('kind',['no_auth','rejected','tampered','wrong_batch'])
def test_review_failures_do_not_complete(queue,kind):
    r = review_saved(queue.load('candidate'))
    authorize = auth
    if kind == 'no_auth': authorize = None
    elif kind == 'rejected': r = review_saved(queue.load('candidate'),decision='rejected')
    elif kind == 'tampered': r = replace(r,rationale='changed')
    elif kind == 'wrong_batch': r = batch('other')[1]
    with pytest.raises((PermissionError,ValueError)): queue.commit('candidate',r,authorize=authorize)
    assert queue.load('candidate').status == 'pending'
    assert queue.store.ledger.revision() == queue.store.load()[1] == 0


def test_committed_retry_still_requires_current_auth(queue):
    r = review_saved(queue.load('candidate'))
    queue.commit('candidate',r,authorize=auth)
    with pytest.raises(PermissionError): queue.commit('candidate',r,authorize=lambda *_:False)


@pytest.mark.parametrize('damage',['payload','digest','status','false_completion','missing_completion'])
def test_corruption_fail_closed(queue,damage):
    if damage == 'missing_completion':
        queue.commit('candidate',review_saved(queue.load('candidate')),authorize=auth)
    sql = {
        'payload': "UPDATE pending_retrievals SET payload='corrupted'",
        'digest': "UPDATE pending_retrievals SET digest='corrupted'",
        'status': "UPDATE pending_retrievals SET operation_id='unrelated'",
        'false_completion': "UPDATE pending_retrievals SET status='committed',operation_id='pending/candidate'",
        'missing_completion': "UPDATE pending_retrievals SET status='pending',operation_id=NULL",
    }[damage]
    with sqlite3.connect(queue.store.ledger.path) as db: db.execute(sql)
    with pytest.raises(ValueError,match='integrity'): queue.load('candidate')
    with pytest.raises(ValueError,match='integrity'): queue.list_pending()


def test_commit_binding_detects_rewritten_candidate_checksum(queue):
    queue.commit('candidate',review_saved(queue.load('candidate')),authorize=auth)
    with sqlite3.connect(queue.store.ledger.path) as db:
        data = json.loads(db.execute('SELECT payload FROM pending_retrievals').fetchone()[0])
        data['state_revision'] = 5
        encoded = _encode(data)
        db.execute('UPDATE pending_retrievals SET payload=?,digest=?',(encoded,_checksum(encoded)))
    with pytest.raises(ValueError,match='binding integrity'): queue.load('candidate')


def test_synthetic_candidate_and_no_reexecution(store):
    called=[]
    candidate = prepare(store,executor=lambda **kw:called.append(True) or output(synthetic=True))
    q = PendingRetrievalQueue(store)
    q.save('synthetic',candidate)
    c = q.load('synthetic')
    q.commit('synthetic',review_saved(c),authorize=auth)
    q.commit('synthetic',review_saved(c),authorize=auth)
    assert len(called) == 1
    state = store.load()[0]
    assert state.evidence['s1']['synthetic'] and 's1' not in state.sources


def test_unknown_invalid_and_nonreviewable(queue):
    with pytest.raises(KeyError): queue.load('absent')
    with pytest.raises(ValueError): queue.save('',prepare(queue.store))
    with pytest.raises(PermissionError): queue.save('stopped',prepare(queue.store,action='stop'))
    with pytest.raises(TypeError): queue.save('bad',{})
    assert len(queue.list_pending()) == 1


def test_saved_candidate_is_detached(queue):
    c = queue.load('candidate')
    c.validation.documents[0].metadata['extra'] = 'caller mutation'
    assert 'extra' not in queue.load('candidate').validation.documents[0].metadata


def test_nonjson_candidate_cannot_be_saved(store):
    q = PendingRetrievalQueue(store)
    candidate = prepare(store)
    # Both copies must match, but payload still must be durable JSON data.
    marker = object()
    candidate.validation.documents[0].metadata['bad'] = marker
    candidate.step.execution.output['documents'][0]['metadata']['bad'] = marker
    with pytest.raises((TypeError,ValueError)): q.save('bad',candidate)
    assert not q.list_pending()


def test_competing_candidates_preserve_loser_as_pending(store):
    q = PendingRetrievalQueue(store)
    q.save('a',prepare(store))
    q.save('b',prepare(store,executor=lambda **kw:output('s2')))
    path = store.ledger.path
    reviews = {cid:review_saved(q.load(cid)) for cid in ('a','b')}
    def run(cid):
        try:
            PendingRetrievalQueue(PersistentEvidenceStore(path)).commit(cid,reviews[cid],authorize=auth)
            return 'committed'
        except RuntimeError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,('a','b')))
    assert results.count('committed') == 1 and results.count('stale state revision') == 1
    assert len(q.list_pending()) == 1 and store.ledger.revision() == 1


def test_retry_after_later_commit(queue):
    r = review_saved(queue.load('candidate'))
    first = queue.commit('candidate',r,authorize=auth)
    ingest(queue.store,'other',expected_state_revision=1,expected_ledger_revision=1)
    assert queue.commit('candidate',r,authorize=auth) == first
    assert queue.store.load()[1] == 2


def test_legacy_database_queue_adoption(tmp_path):
    from pathlib import Path
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript((Path(__file__).parent/'fixtures'/'cycle115_ingested.sql').read_text())
    s=PersistentEvidenceStore(path)
    q=PendingRetrievalQueue(s)
    assert not q.list_pending()
    c=prepare(s,executor=lambda **kw:output('s2'))
    q.save('new',c)
    assert q.commit('new',review_saved(q.load('new')),authorize=auth)['state_revision'] == 2


@pytest.mark.parametrize('field,value', [('candidate_id','other'),('state_revision',True),('ledger_revision',-1),('output',{'status':'failed'})])
def test_invalid_recomputed_payload_rejected(queue,field,value):
    with sqlite3.connect(queue.store.ledger.path) as db:
        data=json.loads(db.execute('SELECT payload FROM pending_retrievals').fetchone()[0])
        data[field]=value
        encoded=_encode(data)
        db.execute('UPDATE pending_retrievals SET payload=?,digest=?',(encoded,_checksum(encoded)))
    with pytest.raises(ValueError,match='integrity'): queue.load('candidate')
