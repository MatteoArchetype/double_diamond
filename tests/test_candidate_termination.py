import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from test_persistent_ingestion import store, auth, batch
from test_persistent_controller import prepare
from test_pending_retrieval import queue, review_saved
from dd_research_runtime.pending_retrieval import PendingRetrievalQueue
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore


def terminal_auth(actor, permission):
    return actor == 'human' and permission in {'evidence_review','evidence_cancel'}


def reject(q, **kwargs):
    options=dict(expected_ledger_revision=0,authorize=terminal_auth)
    options.update(kwargs)
    return q.reject('candidate',review_saved(q.load('candidate'),decision='rejected'),**options)


def cancel(q, **kwargs):
    options=dict(actor='human',rationale='Scope withdrawn',authorize=terminal_auth)
    options.update(kwargs)
    return q.cancel('candidate',**options)


@pytest.mark.parametrize('kind',['rejected','cancelled'])
def test_terminal_lifecycle_restart_and_retry(queue,kind):
    before=queue.store.load()[0].snapshot()
    candidate=prepare(queue.store)
    result=reject(queue) if kind == 'rejected' else cancel(queue)
    reopened=PendingRetrievalQueue(PersistentEvidenceStore(queue.store.ledger.path))
    assert reopened.load('candidate') == result
    assert result.status == kind and result.termination['actor'] == 'human'
    assert not reopened.list_pending()
    assert reopened.save('candidate',candidate).status == kind
    repeated=reject(reopened) if kind == 'rejected' else cancel(reopened)
    assert repeated == result
    assert reopened.store.load()[0].snapshot() == before
    assert reopened.store.load()[1] == 0
    assert reopened.store.ledger.revision() == int(kind == 'rejected')
    if kind == 'rejected': assert reopened.store.ledger.receipts()[0][3] == 'rejected'
    with pytest.raises(PermissionError,match='terminal'):
        reopened.commit('candidate',review_saved(reopened.load('candidate')),authorize=auth)


@pytest.mark.parametrize('kind',['rejected','cancelled'])
@pytest.mark.parametrize('phase',['after_receipt','after_terminal','before_commit'])
@pytest.mark.parametrize('error',[RuntimeError,KeyboardInterrupt])
def test_terminal_failure_rolls_back(queue,kind,phase,error):
    def fail(name):
        if name == phase: raise error('interrupted')
    with pytest.raises(error):
        reject(queue,_fault=fail) if kind == 'rejected' else cancel(queue,_fault=fail)
    assert queue.load('candidate').status == 'pending'
    assert queue.store.ledger.revision() == queue.store.load()[1] == 0
    assert len(queue.list_pending()) == 1


def crash_rejection(path,phase):
    q=PendingRetrievalQueue(PersistentEvidenceStore(path))
    def crash(name):
        if name == phase: os._exit(82)
    reject(q,_fault=crash)


@pytest.mark.parametrize('phase',['after_receipt','after_terminal','before_commit','after_commit'])
def test_rejection_process_death(queue,phase):
    p=multiprocessing.get_context('spawn').Process(target=crash_rejection,args=(queue.store.ledger.path,phase))
    p.start(); p.join(15)
    if p.is_alive(): p.terminate(); p.join(); pytest.fail('crash timeout')
    assert p.exitcode == 82
    q=PendingRetrievalQueue(PersistentEvidenceStore(queue.store.ledger.path))
    committed=phase == 'after_commit'
    assert q.load('candidate').status == ('rejected' if committed else 'pending')
    assert q.store.ledger.revision() == int(committed)
    assert reject(q).status == 'rejected' and q.store.ledger.revision() == 1


@pytest.mark.parametrize('kind',['rejected','cancelled'])
def test_current_authorization_required_even_on_retry(queue,kind):
    action=reject if kind == 'rejected' else cancel
    with pytest.raises(PermissionError): action(queue,authorize=None)
    action(queue)
    with pytest.raises(PermissionError): action(queue,authorize=lambda *_:False)


def test_ingest_authorization_does_not_grant_terminal_permission(queue):
    with pytest.raises(PermissionError): reject(queue,authorize=auth)
    with pytest.raises(PermissionError): cancel(queue,authorize=auth)
    assert queue.load('candidate').status == 'pending'


@pytest.mark.parametrize('damage',['approved','tampered','wrong_batch'])
def test_rejection_review_checks(queue,damage):
    r=review_saved(queue.load('candidate'),decision='rejected')
    if damage == 'approved': r=review_saved(queue.load('candidate'))
    elif damage == 'tampered': r=replace(r,rationale='altered')
    else:
        from dd_research_runtime.evidence_review import review_retrieval
        v=batch('other')[0]
        r=review_retrieval(v,snapshots={'other':dict(text='Exact passage other',location='p1')},reviewer='human',decision='rejected',rationale='No')
    with pytest.raises((ValueError,PermissionError)):
        queue.reject('candidate',r,expected_ledger_revision=0,authorize=terminal_auth)
    assert queue.load('candidate').status == 'pending' and queue.store.ledger.revision() == 0


def test_stale_rejection_revision_and_pending_state(queue):
    queue.store.ledger.append(batch('other')[1],expected_revision=0)
    with pytest.raises(RuntimeError,match='stale ledger'): reject(queue)
    assert queue.load('candidate').status == 'pending'
    assert reject(queue,expected_ledger_revision=1).status == 'rejected'
    assert queue.store.ledger.revision() == 2


@pytest.mark.parametrize('first',['rejected','cancelled','committed'])
def test_terminal_decisions_cannot_be_replaced(queue,first):
    if first == 'rejected': reject(queue)
    elif first == 'cancelled': cancel(queue)
    else: queue.commit('candidate',review_saved(queue.load('candidate')),authorize=auth)
    if first != 'rejected':
        with pytest.raises((ValueError,PermissionError)): reject(queue)
    if first != 'cancelled':
        with pytest.raises((ValueError,PermissionError)): cancel(queue)
    if first == 'cancelled':
        with pytest.raises(ValueError,match='conflict'): cancel(queue,rationale='Different reason')
    assert queue.load('candidate').status == first


@pytest.mark.parametrize('damage',['payload','digest','delete_receipt','false_base_completion'])
def test_terminal_corruption_blocks_queue(queue,damage):
    reject(queue)
    statements={
        'payload': "UPDATE retrieval_terminations SET payload='corrupted'",
        'digest': "UPDATE retrieval_terminations SET digest='corrupted'",
        'delete_receipt': 'DELETE FROM receipts',
        'false_base_completion': "UPDATE pending_retrievals SET status='committed',operation_id='pending/candidate'",
    }
    with sqlite3.connect(queue.store.ledger.path) as db: db.execute(statements[damage])
    with pytest.raises(ValueError,match='integrity'): queue.load('candidate')
    with pytest.raises(ValueError,match='integrity'): queue.list_pending()


def test_concurrent_identical_rejections_one_receipt(queue):
    path=queue.store.ledger.path
    def run(_): return reject(PendingRetrievalQueue(PersistentEvidenceStore(path)))
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(run,range(4)))
    assert all(r == results[0] for r in results)
    assert queue.store.ledger.revision() == 1


@pytest.mark.parametrize('kind',['rejected','cancelled'])
def test_race_approval_and_terminal_has_one_winner(queue,kind):
    path=queue.store.ledger.path
    approved=review_saved(queue.load('candidate'))
    def run(action):
        q=PendingRetrievalQueue(PersistentEvidenceStore(path))
        try:
            if action == 'approve': q.commit('candidate',approved,authorize=auth)
            elif kind == 'rejected': reject(q)
            else: cancel(q)
            return 'success'
        except (PermissionError,ValueError,RuntimeError): return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,('approve','terminate')))
    assert results.count('success') == 1
    status=queue.load('candidate').status
    assert status in {'committed',kind}
    assert bool(queue.store.load()[0].evidence) == (status == 'committed')
    assert queue.store.ledger.revision() == (0 if status == 'cancelled' else 1)


@pytest.mark.parametrize('actor,rationale',[('', 'reason'),('human',''),(None,'reason')])
def test_cancellation_requires_actor_and_reason(queue,actor,rationale):
    with pytest.raises(ValueError): cancel(queue,actor=actor,rationale=rationale)
    assert queue.load('candidate').status == 'pending'


def test_orphan_termination_is_not_silently_ignored(queue):
    cancel(queue)
    with sqlite3.connect(queue.store.ledger.path) as db:
        db.execute('DELETE FROM pending_retrievals')
    with pytest.raises(ValueError,match='orphan termination'): queue.list_pending()


def test_cycle118_queue_schema_adopts_additive_table(queue):
    # Removing the sole new table recreates the unchanged Cycle 118 queue schema.
    path=queue.store.ledger.path
    with sqlite3.connect(path) as db: db.execute('DROP TABLE retrieval_terminations')
    reopened=PendingRetrievalQueue(PersistentEvidenceStore(path))
    assert reopened.load('candidate').status == 'pending'
    assert reject(reopened).status == 'rejected'


def test_rejection_does_not_execute_human_gate(queue):
    reject(queue)
    state=queue.store.load()[0]
    assert state.human_gates['publication']['status'] == 'pending_review'
    assert not state.evidence and not state.sources
