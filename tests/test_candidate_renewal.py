import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from test_persistent_ingestion import store,auth,batch,ingest
from test_pending_retrieval import queue,review_saved
from test_candidate_termination import terminal_auth
from dd_research_runtime.pending_retrieval import PendingRetrievalQueue
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore


def renew_auth(actor,permission):
    return actor == 'human' and permission == 'evidence_renew'


def advance(q):
    ingest(q.store,'other')


def renew(q,child='renewed',**kwargs):
    options=dict(actor='human',rationale='Reconcile current state',expected_state_revision=1,
                 expected_ledger_revision=1,authorize=renew_auth)
    options.update(kwargs)
    return q.renew('candidate',child,**options)


def fresh_review(q,cid='renewed',decision='approved'):
    c=q.load(cid)
    return q.review(cid,snapshots={d.source_id:dict(text=d.passage,location=d.content_location) for d in c.validation.documents},
                    reviewer='human',decision=decision,rationale='Checked renewed context')


def test_renew_restart_fresh_review_commit(queue):
    old=queue.load('candidate')
    old_review=review_saved(old)
    advance(queue)
    child=renew(queue)
    assert child.status == 'pending' and child.review_context
    assert (child.state_revision,child.ledger_revision) == (1,1)
    assert child.validation == old.validation
    parent=queue.load('candidate')
    assert parent.status == 'superseded' and parent.successor_id == 'renewed'
    assert parent.state_revision == 0 and parent.validation == old.validation
    assert [c.candidate_id for c in queue.list_pending()] == ['renewed']
    q=PendingRetrievalQueue(PersistentEvidenceStore(queue.store.ledger.path))
    with pytest.raises(PermissionError,match='candidate-bound'): q.commit('renewed',old_review,authorize=auth)
    r=fresh_review(q)
    result=q.commit('renewed',r,authorize=auth)
    assert result['state_revision'] == result['ledger_revision'] == 2
    assert q.commit('renewed',r,authorize=auth) == result
    assert q.store.load()[0].human_gates['publication']['status'] == 'pending_review'


def test_renewal_idempotent_after_later_commit(queue):
    advance(queue)
    first=renew(queue)
    ingest(queue.store,'third',expected_state_revision=1,expected_ledger_revision=1)
    assert renew(queue) == first
    assert queue.store.ledger.revision() == 2


@pytest.mark.parametrize('phase',['after_child','after_lineage','before_commit'])
@pytest.mark.parametrize('error',[RuntimeError,KeyboardInterrupt])
def test_renewal_rollback(queue,phase,error):
    advance(queue)
    def fail(name):
        if name == phase: raise error('interrupted')
    with pytest.raises(error): renew(queue,_fault=fail)
    assert queue.load('candidate').status == 'pending'
    with pytest.raises(KeyError): queue.load('renewed')
    assert queue.store.load()[1] == queue.store.ledger.revision() == 1


def crash_renew(path,phase):
    q=PendingRetrievalQueue(PersistentEvidenceStore(path))
    def crash(name):
        if name == phase: os._exit(83)
    renew(q,_fault=crash)


@pytest.mark.parametrize('phase',['after_child','after_lineage','before_commit','after_commit'])
def test_process_recovery(queue,phase):
    advance(queue)
    p=multiprocessing.get_context('spawn').Process(target=crash_renew,args=(queue.store.ledger.path,phase))
    p.start();p.join(15)
    if p.is_alive(): p.terminate();p.join();pytest.fail('crash timeout')
    assert p.exitcode == 83
    q=PendingRetrievalQueue(PersistentEvidenceStore(queue.store.ledger.path))
    assert q.load('candidate').status == ('superseded' if phase == 'after_commit' else 'pending')
    assert renew(q).status == 'pending'
    assert q.store.ledger.revision() == 1


@pytest.mark.parametrize('options',[{'authorize':None},{'authorize':auth},{'authorize':lambda *_:1}])
def test_renewal_requires_separate_permission(queue,options):
    advance(queue)
    with pytest.raises(PermissionError): renew(queue,**options)
    assert queue.load('candidate').status == 'pending'


def test_retry_requires_current_permission(queue):
    advance(queue);renew(queue)
    with pytest.raises(PermissionError): renew(queue,authorize=lambda *_:False)


@pytest.mark.parametrize('options',[{'expected_state_revision':0},{'expected_ledger_revision':0}])
def test_current_revision_compare_and_swap(queue,options):
    advance(queue)
    with pytest.raises(RuntimeError,match='stale renewal'): renew(queue,**options)
    assert queue.load('candidate').status == 'pending'


def test_not_stale_cannot_be_renewed(queue):
    with pytest.raises(ValueError,match='not stale'):
        renew(queue,expected_state_revision=0,expected_ledger_revision=0)


def test_ledger_only_staleness(queue):
    queue.store.ledger.append(batch('audit')[1],expected_revision=0)
    child=renew(queue,expected_state_revision=0)
    assert (child.state_revision,child.ledger_revision) == (0,1)
    queue.commit('renewed',fresh_review(queue),authorize=auth)
    assert queue.store.load()[1] == 1 and queue.store.ledger.revision() == 2


def test_superseded_parent_cannot_commit_cancel_or_reject(queue):
    old=queue.load('candidate');r=review_saved(old)
    advance(queue);renew(queue)
    with pytest.raises(PermissionError): queue.commit('candidate',r,authorize=auth)
    with pytest.raises(PermissionError): queue.cancel('candidate',actor='human',rationale='Cancel',authorize=terminal_auth)
    with pytest.raises(PermissionError): queue.reject('candidate',review_saved(old,decision='rejected'),expected_ledger_revision=1,authorize=terminal_auth)
    assert queue.load('candidate').status == 'superseded'


def test_rejected_or_cancelled_candidate_not_renewed(queue):
    queue.cancel('candidate',actor='human',rationale='Cancel',authorize=terminal_auth)
    advance(queue)
    with pytest.raises(PermissionError): renew(queue)


def test_fresh_context_rejection(queue):
    old_rejection=review_saved(queue.load('candidate'),decision='rejected')
    advance(queue);renew(queue)
    with pytest.raises(PermissionError,match='candidate-bound'):
        queue.reject('renewed',old_rejection,expected_ledger_revision=1,authorize=terminal_auth)
    r=fresh_review(queue,decision='rejected')
    assert queue.reject('renewed',r,expected_ledger_revision=1,authorize=terminal_auth).status == 'rejected'
    assert queue.load('renewed').status == 'rejected'


def test_tampered_context_review_integrity(queue):
    advance(queue);renew(queue)
    r=fresh_review(queue)
    r=replace(r,candidate_context='wrong')
    with pytest.raises((PermissionError,ValueError)): queue.commit('renewed',r,authorize=auth)
    assert queue.load('renewed').status == 'pending'


def test_concurrent_identical_renewals(queue):
    advance(queue)
    path=queue.store.ledger.path
    def run(_): return renew(PendingRetrievalQueue(PersistentEvidenceStore(path)))
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(run,range(4)))
    assert all(r == results[0] for r in results)
    assert len(queue.list_pending()) == 1


def test_concurrent_different_children_one_winner(queue):
    advance(queue)
    path=queue.store.ledger.path
    def run(cid):
        try: renew(PendingRetrievalQueue(PersistentEvidenceStore(path)),cid);return 'saved'
        except PermissionError:return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,('a','b')))
    assert results.count('saved') == 1 and results.count('blocked') == 1
    assert len(queue.list_pending()) == 1


def test_lineage_corruption_blocks_reads(queue):
    advance(queue);renew(queue)
    with sqlite3.connect(queue.store.ledger.path) as db:
        db.execute("UPDATE candidate_renewals SET digest='corrupted'")
    with pytest.raises(ValueError,match='renewal integrity'): queue.load('renewed')
    with pytest.raises(ValueError,match='renewal integrity'): queue.list_pending()


def test_multiple_renewals_require_distinct_context(queue):
    advance(queue);first=renew(queue)
    r=fresh_review(queue)
    ingest(queue.store,'third',expected_state_revision=1,expected_ledger_revision=1)
    second=queue.renew('renewed','latest',actor='human',rationale='Changed again',
                      expected_state_revision=2,expected_ledger_revision=2,authorize=renew_auth)
    assert second.review_context != first.review_context
    with pytest.raises(PermissionError): queue.commit('latest',r,authorize=auth)
    queue.commit('latest',fresh_review(queue,'latest'),authorize=auth)
    assert queue.store.load()[1] == 3


@pytest.mark.parametrize('field,value',[('child', 'candidate'),('actor',''),('rationale',''),('expected_state_revision',True),('expected_ledger_revision',-1)])
def test_invalid_renewal_inputs(queue,field,value):
    advance(queue)
    options={field:value}
    with pytest.raises(ValueError): renew(queue,**options)
    assert queue.load('candidate').status == 'pending'


def test_conflicting_retry(queue):
    advance(queue);renew(queue)
    with pytest.raises(ValueError,match='conflict'): renew(queue,rationale='Different reason')
    assert queue.load('candidate').successor_id == 'renewed'


def test_renewed_candidate_cancellation_and_auth_still_required(queue):
    advance(queue);renew(queue)
    queue.cancel('renewed',actor='human',rationale='Withdrawn',authorize=terminal_auth)
    assert queue.load('renewed').status == 'cancelled'
    with pytest.raises(PermissionError): queue.commit('renewed',review_saved(queue.load('renewed')),authorize=auth)


def test_renewed_review_requires_source_fidelity_and_ingest_auth(queue):
    advance(queue);renew(queue)
    with pytest.raises(ValueError,match='not verified'):
        queue.review('renewed',snapshots={'s1':dict(text='Wrong passage',location='p1')},
                     reviewer='human',decision='approved',rationale='Check')
    r=fresh_review(queue)
    with pytest.raises(PermissionError): queue.commit('renewed',r,authorize=renew_auth)
    assert queue.load('renewed').status == 'pending'


def test_lineage_orphan_detected(queue):
    advance(queue);renew(queue)
    with sqlite3.connect(queue.store.ledger.path) as db:
        db.execute("DELETE FROM pending_retrievals WHERE candidate_id='renewed'")
    with pytest.raises(ValueError,match='renewal integrity'): queue.list_pending()


def test_race_renewal_and_cancel_one_winner(queue):
    advance(queue)
    path=queue.store.ledger.path
    def run(action):
        q=PendingRetrievalQueue(PersistentEvidenceStore(path))
        try:
            if action == 'renew': renew(q)
            else: q.cancel('candidate',actor='human',rationale='Withdraw',authorize=terminal_auth)
            return 'success'
        except (ValueError,PermissionError): return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,('renew','cancel')))
    assert results.count('success') == 1
    assert queue.load('candidate').status in {'superseded','cancelled'}
    assert queue.store.ledger.revision() == 1

