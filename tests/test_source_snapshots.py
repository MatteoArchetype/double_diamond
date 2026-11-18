import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_persistent_ingestion import store,auth,batch,ingest
from test_pending_retrieval import queue,review_saved
from test_candidate_renewal import advance,renew,fresh_review
from test_persistent_controller import prepare,review,commit
from dd_research_runtime.evidence_review import review_retrieval
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore,_encode,_checksum


def snapshots(sid='s1'):
    return {sid:dict(text='Exact passage '+sid,location='p1')}


def test_retain_reopen_recheck_and_read_isolation(store):
    result=ingest(store,source_snapshots=snapshots())
    s=PersistentEvidenceStore(store.ledger.path)
    assert s.load_source_snapshots('s1') == snapshots()
    assert s.load_review('s1')['source_snapshots'] == snapshots()
    assert s.snapshot_coverage() == dict(legacy_operations=0,retained_snapshot_sets=1,reviews_without_snapshots=0,snapshots=1)
    local=s.load_source_snapshots('s1');local['s1']['text']='changed locally'
    assert s.load_source_snapshots('s1') == snapshots()
    assert ingest(s,source_snapshots=snapshots()) == result


def test_without_snapshots_remains_explicit(store):
    ingest(store)
    assert store.snapshot_coverage() == dict(legacy_operations=0,retained_snapshot_sets=0,reviews_without_snapshots=1,snapshots=0)
    with pytest.raises(LookupError,match='not retained'):store.load_source_snapshots('s1')
    with pytest.raises(KeyError):store.load_source_snapshots('unknown')


def test_legacy_gap_not_backfilled(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as db:db.executescript((Path(__file__).parent/'fixtures'/'cycle115_ingested.sql').read_text())
    s=PersistentEvidenceStore(path)
    assert s.snapshot_coverage()['legacy_operations'] == 1
    with pytest.raises(LookupError,match='legacy'):s.load_source_snapshots('s1')
    assert ingest(s)['state_revision'] == 1
    assert s.snapshot_coverage()['legacy_operations'] == 1


@pytest.mark.parametrize('raw',[
    {}, [], {'missing':dict(text='Exact passage s1',location='p1')},
    {'s1':dict(text='wrong passage',location='p1')},
    {'s1':dict(text='Exact passage s1',location='p2')},
    {'s1':dict(text=123,location='p1')}, {'s1':dict(text='Exact passage s1',location=None)},
    {'s1':dict(text='Exact passage s1',location='p1',extra='unrequested')},
    {'s1':dict(text='Prefix Exact passage s1 suffix',location='p1')},
    {**snapshots(),'extra':dict(text='unrelated',location='x')},
])
def test_mismatched_snapshot_input_fails_before_mutation(store,raw):
    with pytest.raises(ValueError):ingest(store,source_snapshots=raw)
    assert store.load()[1] == store.ledger.revision() == 0
    assert store.snapshot_coverage()['retained_snapshot_sets'] == 0


def test_full_snapshot_text_matches_original_review_hash(store):
    v,_=batch()
    raw={'s1':dict(text='Prefix Exact passage s1 suffix',location='p1')}
    r=review_retrieval(v,snapshots=raw,reviewer='human',decision='approved',rationale='Full source checked')
    store.ingest(v,r,operation_id='full',expected_state_revision=0,expected_ledger_revision=0,authorize=auth,source_snapshots=raw)
    assert store.load_source_snapshots('full') == raw


@pytest.mark.parametrize('initial', [False,True])
def test_retention_choice_is_part_of_retry_identity(store,initial):
    ingest(store,source_snapshots=snapshots() if initial else None)
    with pytest.raises(ValueError,match='different request'):
        ingest(store,source_snapshots=None if initial else snapshots())
    assert store.load()[1] == 1


@pytest.mark.parametrize('phase',['after_receipt','after_state','after_review_archive','before_commit'])
def test_snapshot_retention_rolls_back_with_evidence(store,phase):
    def fail(name):
        if name == phase:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):ingest(store,source_snapshots=snapshots(),_fault=fail)
    assert store.snapshot_coverage()['retained_snapshot_sets'] == 0
    assert store.load()[1] == store.ledger.revision() == 0


def crash_worker(path,phase):
    def crash(name):
        if name == phase:os._exit(85)
    ingest(PersistentEvidenceStore(path),source_snapshots=snapshots(),_fault=crash)


@pytest.mark.parametrize('phase',['after_review_archive','after_commit'])
def test_snapshot_process_death_recovery(store,phase):
    p=multiprocessing.get_context('spawn').Process(target=crash_worker,args=(store.ledger.path,phase))
    p.start();p.join(15)
    if p.is_alive():p.terminate();p.join();pytest.fail('crash timeout')
    assert p.exitcode == 85
    s=PersistentEvidenceStore(store.ledger.path)
    assert s.snapshot_coverage()['retained_snapshot_sets'] == int(phase == 'after_commit')
    ingest(s,source_snapshots=snapshots())
    assert s.load_source_snapshots('s1') == snapshots()


def test_queue_retention_preserves_gate_and_state(queue):
    queue.commit('candidate',review_saved(queue.load('candidate')),authorize=auth,source_snapshots=snapshots())
    assert queue.store.load_source_snapshots('pending/candidate') == snapshots()
    assert queue.load('candidate').status == 'committed'
    assert queue.store.load()[0].human_gates['publication']['status'] == 'pending_review'


def test_renewed_context_and_snapshot_retained_together(queue):
    advance(queue);c=renew(queue)
    queue.commit('renewed',fresh_review(queue),authorize=auth,source_snapshots=snapshots())
    data=queue.store.load_review('pending/renewed')
    assert data['review']['candidate_context'] == c.review_context
    assert data['source_snapshots'] == snapshots()


def test_controller_bridge_supports_retention(store):
    c=prepare(store)
    commit(store,c,review(c),source_snapshots=snapshots())
    assert store.load_source_snapshots('controller-s1') == snapshots()


def test_synthetic_snapshot_does_not_gain_real_source(store):
    v,r=batch(synthetic=True)
    store.ingest(v,r,operation_id='synthetic',expected_state_revision=0,expected_ledger_revision=0,authorize=auth,source_snapshots=snapshots())
    state,_=store.load()
    assert state.evidence['s1']['synthetic'] and 's1' not in state.sources
    assert store.load_source_snapshots('synthetic') == snapshots()


@pytest.mark.parametrize('damage',['text','location','remove'])
def test_recomputed_archive_checksum_still_checks_review_binding(store,damage):
    ingest(store,source_snapshots=snapshots())
    with sqlite3.connect(store.ledger.path) as db:
        data=json.loads(db.execute('SELECT payload FROM ingestion_review_archive').fetchone()[0])
        if damage == 'text':data['source_snapshots']['s1']['text']='Prefix Exact passage s1 suffix'
        elif damage == 'location':data['source_snapshots']['s1']['location']='p2'
        else:del data['source_snapshots']['s1']
        encoded=_encode(data);digest=_checksum(encoded)
        db.execute('UPDATE ingestion_review_archive SET payload=?,digest=?',(encoded,digest))
        db.execute('UPDATE ingestion_operations SET request_digest=?',(digest,))
    with pytest.raises(ValueError,match='review archive integrity'):store.load()


def test_concurrent_identical_snapshot_commit_is_idempotent(store):
    path=store.ledger.path
    def run(_):return ingest(PersistentEvidenceStore(path),source_snapshots=snapshots())
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,range(4)))
    assert all(r == results[0] for r in results)
    assert store.snapshot_coverage()['retained_snapshot_sets'] == 1


def test_retention_does_not_bypass_authorization(store):
    with pytest.raises(PermissionError):ingest(store,source_snapshots=snapshots(),authorize=lambda *_:False)
    assert store.snapshot_coverage()['retained_snapshot_sets'] == 0


def test_multidocument_snapshot_order_and_full_text(store):
    from dataclasses import replace
    first,_=batch('s1');second,_=batch('s2')
    v=replace(first,documents=first.documents+second.documents)
    raw={'s2':dict(text='Unicode context æøå Exact passage s2',location='p1'),
         's1':dict(text='Prefix Exact passage s1 suffix',location='p1')}
    r=review_retrieval(v,snapshots=raw,reviewer='human',decision='approved',rationale='Both independent fixtures checked')
    store.ingest(v,r,operation_id='multi',expected_state_revision=0,expected_ledger_revision=0,authorize=auth,source_snapshots=raw)
    assert store.load_source_snapshots('multi') == raw
    assert store.snapshot_coverage()['snapshots'] == 2
