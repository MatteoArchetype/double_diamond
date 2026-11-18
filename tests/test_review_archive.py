import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_persistent_ingestion import store,auth,batch,ingest
from test_pending_retrieval import queue
from test_candidate_renewal import advance,renew,fresh_review
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore,_encode,_checksum


def test_archive_full_review_reopen_and_isolation(store):
    v,r=batch()
    ingest(store)
    s=PersistentEvidenceStore(store.ledger.path)
    data=s.load_review('s1')
    assert data['review']['record_digest'] == r.record_digest
    assert data['review']['snapshot_digests'] == list(r.snapshot_digests)
    assert data['review']['reviewer'] == 'human'
    assert data['documents'] == [d.to_evidence_payload() for d in v.documents]
    data['review']['rationale']='local mutation'
    assert s.load_review('s1')['review']['rationale'] == r.rationale
    assert s.review_coverage() == dict(legacy_operations=0,retained_reviews=1,legacy_state_revision=0)
    assert ingest(s)['state_revision'] == 1


def test_legacy_coverage_and_new_write(tmp_path):
    path=tmp_path/'legacy.db'
    fixture=Path(__file__).parent/'fixtures'/'cycle115_ingested.sql'
    with sqlite3.connect(path) as db: db.executescript(fixture.read_text())
    s=PersistentEvidenceStore(path)
    assert s.review_coverage() == dict(legacy_operations=1,retained_reviews=0,legacy_state_revision=1)
    with pytest.raises(LookupError,match='legacy'): s.load_review('s1')
    assert ingest(s)['state_revision'] == 1 # Identical legacy retry never fabricates a review.
    ingest(s,'s2',expected_state_revision=1,expected_ledger_revision=1)
    assert s.review_coverage() == dict(legacy_operations=1,retained_reviews=1,legacy_state_revision=1)
    assert s.load_review('s2')['review']['decision'] == 'approved'


def test_unknown_review_and_empty_coverage(store):
    assert store.review_coverage()['retained_reviews'] == 0
    with pytest.raises(KeyError): store.load_review('unknown')


@pytest.mark.parametrize('error',[RuntimeError,KeyboardInterrupt])
def test_archive_fault_rolls_back_all_records(store,error):
    def fail(phase):
        if phase == 'after_review_archive':raise error('interrupted')
    with pytest.raises(error):ingest(store,_fault=fail)
    assert store.load()[1] == store.ledger.revision() == 0
    assert store.review_coverage()['retained_reviews'] == 0
    ingest(store)
    assert store.review_coverage()['retained_reviews'] == 1


def crash_worker(path,phase):
    def crash(name):
        if name == phase:os._exit(84)
    ingest(PersistentEvidenceStore(path),_fault=crash)


@pytest.mark.parametrize('phase',['after_review_archive','after_commit'])
def test_process_crash_archive_atomicity(store,phase):
    p=multiprocessing.get_context('spawn').Process(target=crash_worker,args=(store.ledger.path,phase))
    p.start();p.join(15)
    if p.is_alive():p.terminate();p.join();pytest.fail('crash timeout')
    assert p.exitcode == 84
    s=PersistentEvidenceStore(store.ledger.path)
    committed=int(phase == 'after_commit')
    assert s.review_coverage()['retained_reviews'] == s.load()[1] == s.ledger.revision() == committed
    ingest(s)
    assert s.review_coverage()['retained_reviews'] == 1


@pytest.mark.parametrize('damage',['delete_archive','payload','digest','request_digest','orphan','policy','delete_policy'])
def test_partial_corruption_fail_closed(store,damage):
    ingest(store)
    sql={
        'delete_archive':'DELETE FROM ingestion_review_archive',
        'payload':"UPDATE ingestion_review_archive SET payload='broken'",
        'digest':"UPDATE ingestion_review_archive SET digest='broken'",
        'request_digest':"UPDATE ingestion_operations SET request_digest='"+'a'*64+"'",
        'orphan':"UPDATE ingestion_review_archive SET operation_id='missing'",
        'policy':"UPDATE review_archive_policy SET digest='broken'",
        'delete_policy':'DELETE FROM review_archive_policy',
    }[damage]
    with sqlite3.connect(store.ledger.path) as db:db.execute(sql)
    for action in (store.load,store.verify_integrity,store.review_coverage,lambda:store.load_review('s1'),lambda:ingest(store)):
        with pytest.raises(ValueError,match='integrity'):action()
    if damage == 'delete_policy':
        with pytest.raises(ValueError,match='policy integrity'):PersistentEvidenceStore(store.ledger.path)


@pytest.mark.parametrize('field,value',[('rationale','rewritten'),('snapshot_digests',[]),('candidate_context','forged')])
def test_recomputed_checksum_does_not_hide_review_change(store,field,value):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:
        data=json.loads(db.execute('SELECT payload FROM ingestion_review_archive').fetchone()[0])
        data['review'][field]=value
        encoded=_encode(data)
        db.execute('UPDATE ingestion_review_archive SET payload=?,digest=?',(encoded,_checksum(encoded)))
    with pytest.raises(ValueError,match='integrity'):store.load()


def test_new_archive_cannot_be_downgraded_as_legacy(store):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:
        data=dict(version=1,legacy_state_revision=1)
        encoded=_encode(data)
        db.execute('UPDATE review_archive_policy SET payload=?,digest=?',(encoded,_checksum(encoded)))
    with pytest.raises(ValueError,match='legacy review archive'):store.load()


def test_context_retained_and_bound_to_lineage(queue):
    advance(queue);child=renew(queue)
    r=fresh_review(queue)
    queue.commit('renewed',r,authorize=auth)
    data=queue.store.load_review('pending/renewed')
    assert data['review']['candidate_context'] == child.review_context
    with sqlite3.connect(queue.store.ledger.path) as db:
        db.execute("UPDATE candidate_renewals SET digest='different'")
    with pytest.raises(ValueError,match='context mismatch'):queue.store.load()


def test_concurrent_identical_ingestion_retains_one_review(store):
    path=store.ledger.path
    def run(_):return ingest(PersistentEvidenceStore(path))
    with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(run,range(5)))
    assert all(r == results[0] for r in results)
    assert store.review_coverage()['retained_reviews'] == 1


def test_archive_schema_loss_not_treated_as_new_adoption(store):
    with sqlite3.connect(store.ledger.path) as db:db.execute('DROP TABLE ingestion_review_archive')
    with pytest.raises(ValueError,match='schema integrity'):PersistentEvidenceStore(store.ledger.path)


@pytest.mark.parametrize('mutation',['review','documents'])
def test_archive_recomputes_review_and_batch_digests(store,mutation):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:
        data=json.loads(db.execute('SELECT payload FROM ingestion_review_archive').fetchone()[0])
        if mutation == 'review':data['review']['rationale']='changed'
        else:data['documents'][0]['finding']='changed passage'
        encoded=_encode(data);digest=_checksum(encoded)
        db.execute('UPDATE ingestion_review_archive SET payload=?,digest=?',(encoded,digest))
        db.execute('UPDATE ingestion_operations SET request_digest=?',(digest,))
    with pytest.raises(ValueError,match='review or batch mismatch'):store.load()


def test_queue_archive_fault_rolls_back_completion(queue):
    from test_pending_retrieval import review_saved
    r=review_saved(queue.load('candidate'))
    def fail(phase):
        if phase == 'after_review_archive':raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):queue.commit('candidate',r,authorize=auth,_fault=fail)
    assert queue.load('candidate').status == 'pending'
    assert queue.store.review_coverage()['retained_reviews'] == 0
    queue.commit('candidate',r,authorize=auth)
    assert queue.store.load_review('pending/candidate')['review']['record_digest'] == r.record_digest


def test_archive_absence_cannot_be_recovered_from_retry_claim(store):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute('DELETE FROM ingestion_review_archive')
    with pytest.raises(ValueError,match='missing review archive'):ingest(store)
    with sqlite3.connect(store.ledger.path) as db:
        assert db.execute('SELECT COUNT(*) FROM ingestion_review_archive').fetchone()[0] == 0


def test_cycle120_context_review_remains_explicit_legacy_coverage(tmp_path):
    from dd_research_runtime.pending_retrieval import PendingRetrievalQueue
    path=tmp_path/'cycle120.db'
    fixture=Path(__file__).parent/'fixtures'/'cycle120_renewed.sql'
    with sqlite3.connect(path) as db:db.executescript(fixture.read_text())
    s=PersistentEvidenceStore(path);q=PendingRetrievalQueue(s)
    assert q.load('candidate').status == 'superseded'
    assert q.load('renewed').status == 'committed'
    assert q.load('renewed').review_context
    assert s.review_coverage() == dict(legacy_operations=2,retained_reviews=0,legacy_state_revision=2)
    with pytest.raises(LookupError,match='legacy'):s.load_review('pending/renewed')
    ingest(s,'new',expected_state_revision=2,expected_ledger_revision=2)
    assert s.review_coverage()['retained_reviews'] == 1
