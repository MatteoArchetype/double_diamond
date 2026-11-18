import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from assessment import DIMENSIONS
from test_persistent_ingestion import store,ingest,auth,batch
from test_pending_retrieval import queue,review_saved
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore,_encode,_checksum
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint,verify_database


def analysis_auth(actor,permission):return actor == 'analyst' and permission == 'analysis_write'


def add_claim(cid='C1'):
    return dict(type='add_claim',record=dict(claim_id=cid,claim='Bounded fixture claim',claim_type='descriptive',disposition='draft',status='draft',evidence_ids=['s1']))


def commands():
    return [add_claim(),add_claim('C2'),
        dict(type='assess_evidence',assessment_id='A1',evidence_id='s1',claim_id='C1',dimensions={d:'high' for d in DIMENSIONS},limitations=['Fixture source only'],rationale='Advisory fixture assessment'),
        dict(type='add_contradiction',record=dict(contradiction_id='X1',claim_a='C1',claim_b='C2',issue='Different fixture interpretations',disposition='unresolved')),
        dict(type='update_contradiction',contradiction_id='X1',patch=dict(disposition='qualified',resolution_basis='Different stated scopes')),
        dict(type='put_uncertainty',record=dict(uncertainty_id='U1',question='Does it transfer?',status='open')),
        dict(type='put_uncertainty',record=dict(uncertainty_id='U1',question='Does it transfer?',status='resolved',resolution_basis='Only fixture scope is supported')),
        dict(type='update_claim',claim_id='C1',patch=dict(confidence='medium',claim='Qualified bounded fixture claim')),
        dict(type='set_disposition',disposition_id='D1',claim_id='C1',disposition='qualify',rationale='Limit to fixture scope',evidence_ids=['s1'],prior_status='draft',new_status='qualified',material_uncertainties=['U1'],decision_relevance='Fixture only')]


def apply(store,changes=None,**kwargs):
    options=dict(operation_id='analysis-1',actor='analyst',rationale='Fixture analysis',expected_state_revision=1,authorize=analysis_auth)
    options.update(kwargs)
    return store.apply_analysis(commands() if changes is None else changes,**options)


def test_analysis_roundtrip_advisory_audit_and_checkpoint(store,tmp_path):
    ingest(store)
    before=store.load()[0].snapshot()
    result=apply(store)
    reopened=PersistentEvidenceStore(store.ledger.path)
    state,revision=reopened.load()
    assert revision == result['state_revision'] == 2 and reopened.ledger.revision() == 1
    assert state.claims['C1']['status'] == 'qualified'
    assert state.claims['C1']['confidence'] == 'medium' and len(state.claims['C1']['belief_history']) == 2
    assert state.assessments['A1']['status'] == state.claim_dispositions['D1']['status'] == 'advisory'
    assert state.contradictions['X1']['resolution_basis'] and state.uncertainties['U1']['status'] == 'resolved'
    assert state.evidence == before['evidence'] and state.sources == before['sources'] and state.human_gates == before['human_gates']
    audit=reopened.load_analysis_operation('analysis-1')
    assert audit['request']['actor'] == 'analyst' and audit['request']['commands'] == commands()
    assert len(audit['entry_hash']) == 64
    assert reopened.mutation_coverage() == dict(adoption_revision=0,ingestion_mutations=1,analysis_mutations=1,journal_entries=2)
    backup=tmp_path/'analysis.zip';create_checkpoint(reopened,backup)
    restored=tmp_path/'analysis.db';restore_checkpoint(backup,restored)
    assert PersistentEvidenceStore(restored).load()[0].snapshot() == state.snapshot()
    assert verify_database(restored)['state_revision'] == 2


def test_analysis_and_ingestion_can_interleave_and_retry(store):
    first=ingest(store);result=apply(store,[add_claim()])
    ingest(store,'s2',expected_state_revision=2,expected_ledger_revision=1)
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(evidence_ids=['s1','s2']))],operation_id='analysis-2',expected_state_revision=3)
    assert store.load()[1] == 4 and store.ledger.revision() == 2
    assert ingest(store) == first and apply(store,[add_claim()]) == result
    assert store.review_coverage()['retained_reviews'] == 2


@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit'])
@pytest.mark.parametrize('error',[RuntimeError,KeyboardInterrupt])
def test_analysis_failure_atomicity(store,phase,error):
    ingest(store);before=store.load()[0].snapshot()
    def fail(name):
        if name == phase:raise error('interrupted')
    with pytest.raises(error):apply(store,_fault=fail)
    assert store.load()[0].snapshot() == before and store.load()[1] == 1 and store.ledger.revision() == 1
    assert store.mutation_coverage()['analysis_mutations'] == 0
    assert apply(store)['state_revision'] == 2


def crash_analysis(path,phase):
    def crash(name):
        if name == phase:os._exit(87)
    apply(PersistentEvidenceStore(path),_fault=crash)


@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
def test_analysis_process_recovery(store,phase):
    ingest(store)
    p=multiprocessing.get_context('spawn').Process(target=crash_analysis,args=(store.ledger.path,phase))
    p.start();p.join(15)
    if p.is_alive():p.terminate();p.join();pytest.fail('crash timeout')
    assert p.exitcode == 87
    s=PersistentEvidenceStore(store.ledger.path)
    assert s.load()[1] == (2 if phase == 'after_commit' else 1)
    apply(s)
    assert s.mutation_coverage()['analysis_mutations'] == 1 and s.load()[1] == 2


def test_later_command_failure_does_not_save_earlier_claim(store):
    ingest(store)
    bad=[add_claim(),dict(type='add_contradiction',record=dict(contradiction_id='bad',claim_a='C1',claim_b='missing',issue='Invalid'))]
    with pytest.raises(ValueError):apply(store,bad)
    assert store.load()[0].claims == {} and store.load()[1] == 1


@pytest.mark.parametrize('changes',[
    [dict(type='delete_evidence',evidence_id='s1')],
    [dict(type='approve_gate',gate_id='publication')],
    [dict(type='update_claim',claim_id='C1',patch=dict(human_gates={}))],
    [dict(type='put_uncertainty',record=dict(uncertainty_id='U',question='Question',status='resolved'))],
])
def test_invalid_or_privileged_commands_rejected(store,changes):
    ingest(store)
    with pytest.raises(ValueError):apply(store,changes)
    assert store.load()[1] == 1


@pytest.mark.parametrize('permission',[None,auth,lambda *_:1])
def test_separate_analysis_authorization(store,permission):
    ingest(store)
    with pytest.raises(PermissionError):apply(store,authorize=permission)
    assert store.load()[1] == 1


def test_stale_revision_conflicts_and_retry_authorization(store):
    ingest(store);first=apply(store,[add_claim()])
    with pytest.raises(RuntimeError,match='stale'):apply(store,[add_claim('C2')],operation_id='later')
    with pytest.raises(ValueError,match='different'):apply(store,[add_claim('C2')])
    with pytest.raises(PermissionError):apply(store,[add_claim()],authorize=lambda *_:False)
    assert apply(store,[add_claim()]) == first


def test_global_operation_id_collision(store):
    ingest(store)
    with pytest.raises(ValueError,match='ingestion'):apply(store,[add_claim()],operation_id='s1')
    apply(store,[add_claim()])
    with pytest.raises(ValueError,match='analysis'):
        store.ingest(*batch('other'),operation_id='analysis-1',expected_state_revision=2,expected_ledger_revision=1,authorize=auth)


@pytest.mark.parametrize('same',[False,True])
def test_concurrent_analysis_connections(store,same):
    ingest(store);path=store.ledger.path
    def run(i):
        try:return apply(PersistentEvidenceStore(path),[add_claim('C1' if same else 'C'+str(i))],operation_id='same' if same else 'op'+str(i))
        except RuntimeError:return 'stale'
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,range(4)))
    successes=[r for r in results if isinstance(r,dict)]
    assert len(successes) == (4 if same else 1)
    assert store.load()[1] == 2 and store.mutation_coverage()['analysis_mutations'] == 1


def test_saved_review_stales_after_analysis(queue):
    # An advisory uncertainty can be recorded before the first evidence ingestion.
    queue.store.apply_analysis([dict(type='put_uncertainty',record=dict(uncertainty_id='U1',question='What remains?',status='open'))],operation_id='uncertainty',actor='analyst',rationale='Frame the question',expected_state_revision=0,authorize=analysis_auth)
    with pytest.raises(RuntimeError,match='stale state'):
        queue.commit('candidate',review_saved(queue.load('candidate')),authorize=auth)
    assert queue.load('candidate').status == 'pending' and queue.store.ledger.revision() == 0


def test_synthetic_claim_and_assessment_cannot_be_promoted_to_real(store):
    store.ingest(*batch(synthetic=True),operation_id='synthetic',expected_state_revision=0,expected_ledger_revision=0,authorize=auth)
    apply(store,commands()[:3])
    state,_=store.load()
    assert state.claims['C1']['evidence_origin'] == state.assessments['A1']['evidence_origin'] == 'synthetic_only'
    assert not state.sources and state.evidence['s1']['synthetic'] is True


def test_update_cannot_bypass_required_human_disposition(store):
    ingest(store);apply(store,[add_claim()])
    with pytest.raises(ValueError):apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(disposition='withdraw'))],operation_id='bypass',expected_state_revision=2)
    command=dict(type='set_disposition',disposition_id='withdraw',claim_id='C1',disposition='withdraw',rationale='Change',evidence_ids=['s1'],prior_status='draft',new_status='withdrawn',material_uncertainties=[],decision_relevance='Fixture')
    with pytest.raises(PermissionError):apply(store,[command],operation_id='withdraw',expected_state_revision=2)
    assert store.load()[0].claims['C1']['status'] == 'draft'


def test_legacy_migration_and_retry_history(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as db:db.executescript((Path(__file__).parent/'fixtures'/'cycle115_ingested.sql').read_text())
    s=PersistentEvidenceStore(path)
    assert s.mutation_coverage()['adoption_revision'] == 1
    assert ingest(s)['state_revision'] == 1
    apply(s,[add_claim()])
    assert s.load()[1] == 2 and s.review_coverage()['legacy_operations'] == 1
    assert s.mutation_coverage()['analysis_mutations'] == 1


@pytest.mark.parametrize('damage',['delete_row','request','state','entry_hash','policy'])
def test_mutation_corruption_blocks_reads(store,damage):
    ingest(store);apply(store,[add_claim()])
    sql={
        'delete_row':"DELETE FROM state_mutations WHERE kind='analysis'",
        'request':"UPDATE state_mutations SET request='corrupted' WHERE kind='analysis'",
        'state':"UPDATE state_mutations SET after_snapshot='corrupted' WHERE kind='analysis'",
        'entry_hash':"UPDATE state_mutations SET entry_hash='corrupted' WHERE kind='analysis'",
        'policy':"UPDATE state_journal_policy SET digest='corrupted'",
    }[damage]
    with sqlite3.connect(store.ledger.path) as db:db.execute(sql)
    with pytest.raises(ValueError,match='integrity'):store.load()


def test_recomputed_state_checksum_cannot_hide_analysis_change(store):
    ingest(store);apply(store,[add_claim()])
    with sqlite3.connect(store.ledger.path) as db:
        state=json.loads(db.execute('SELECT snapshot FROM research_state').fetchone()[0]);state['claims']['C1']['claim']='rewritten'
        encoded=_encode(state);db.execute('UPDATE research_state SET snapshot=?,digest=?',(encoded,_checksum(encoded)))
    with pytest.raises(ValueError,match='journal integrity'):store.load()


def analysis_race_worker(path,cid,ready,go,output):
    s=PersistentEvidenceStore(path);ready.put(True)
    if not go.wait(10):output.put('timeout');return
    try:apply(s,[add_claim(cid)],operation_id='op-'+cid);output.put('committed')
    except RuntimeError:output.put('stale')


def test_concurrent_analysis_processes(store):
    ingest(store)
    ctx=multiprocessing.get_context('spawn');ready=ctx.Queue();output=ctx.Queue();go=ctx.Event()
    workers=[ctx.Process(target=analysis_race_worker,args=(store.ledger.path,'C'+str(i),ready,go,output)) for i in range(3)]
    try:
        for p in workers:p.start()
        for _ in workers:assert ready.get(timeout=15)
        go.set();results=[output.get(timeout=15) for _ in workers]
        assert results.count('committed') == 1 and results.count('stale') == 2
    finally:
        for p in workers:
            p.join(5)
            if p.is_alive():p.terminate();p.join()
        ready.close();output.close()
    assert store.mutation_coverage()['analysis_mutations'] == 1 and store.load()[1] == 2


def test_replay_detects_coherent_snapshot_checksum_rewrite(store):
    ingest(store);apply(store,[add_claim()])
    with sqlite3.connect(store.ledger.path) as db:
        row=db.execute("SELECT revision,operation_id,kind,request_digest,result_digest,before_hash,after_snapshot,timestamp,previous_hash FROM state_mutations WHERE kind='analysis'").fetchone()
        sr,oid,kind,reqhash,reshash,before,after,timestamp,previous=row
        state=json.loads(after);state['claims']['C1']['claim']='A rewritten claim'
        encoded=_encode(state);afterhash=_checksum(encoded)
        event=dict(revision=sr,operation_id=oid,kind=kind,request_digest=reqhash,result_digest=reshash,before_hash=before,after_hash=afterhash,timestamp=timestamp,previous_hash=previous)
        db.execute("UPDATE state_mutations SET after_snapshot=?,after_hash=?,entry_hash=? WHERE kind='analysis'",(encoded,afterhash,_checksum(_encode(event))))
        db.execute('UPDATE research_state SET snapshot=?,digest=?',(encoded,afterhash))
    with pytest.raises(ValueError,match='replayed state mismatch'):store.load()


def test_ingestion_journal_failure_rolls_back_complete_new_write(store):
    def fail(phase):
        if phase == 'after_journal':raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):ingest(store,_fault=fail)
    assert store.load()[1] == store.ledger.revision() == 0
    assert store.mutation_coverage()['journal_entries'] == 0


@pytest.mark.parametrize('table',['state_journal_policy','state_mutations'])
def test_journal_schema_loss_not_readopted(store,table):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute('DROP TABLE '+table)
    with pytest.raises(ValueError,match='journal schema'):PersistentEvidenceStore(store.ledger.path)


def test_missing_journal_policy_not_recreated(store):
    with sqlite3.connect(store.ledger.path) as db:db.execute('DELETE FROM state_journal_policy')
    with pytest.raises(ValueError,match='missing state journal'):PersistentEvidenceStore(store.ledger.path)


def test_claim_cannot_start_with_fake_approved_status(store):
    ingest(store);command=add_claim();command['record']['status']='published'
    with pytest.raises(ValueError):apply(store,[command])
    assert store.load()[0].claims == {}


def test_assessment_cannot_claim_approval_or_omit_dimensions(store):
    ingest(store)
    c=commands()[:3];c[2]['dimensions'].pop('claim_fitness')
    with pytest.raises(ValueError,match='dimensions'):apply(store,c)
    assert store.load()[0].claims == {}


def test_unknown_analysis_audit_record_is_explicit(store):
    with pytest.raises(KeyError):store.load_analysis_operation('unknown')


def test_invalid_legacy_state_not_anchored_as_valid_journal(tmp_path):
    path=tmp_path/'corrupt-legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript((Path(__file__).parent/'fixtures'/'cycle115_ingested.sql').read_text())
        db.execute("UPDATE research_state SET digest='corrupted'")
    with pytest.raises(ValueError,match='state integrity'):PersistentEvidenceStore(path)
    with sqlite3.connect(path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='state_journal_policy'").fetchone()


def test_analysis_cannot_relabel_a_claim_as_real_evidence(store):
    store.ingest(*batch(synthetic=True),operation_id='synthetic',expected_state_revision=0,expected_ledger_revision=0,authorize=auth)
    command=add_claim();command['record']['evidence_origin']='non_synthetic'
    with pytest.raises(ValueError):apply(store,[command])
    assert store.load()[0].claims == {}


def test_stale_disposition_prior_status_is_rejected(store):
    ingest(store);apply(store,[add_claim()])
    command=commands()[-1];command['prior_status']='qualified'
    with pytest.raises(ValueError,match='prior claim status'):apply(store,[command],operation_id='bad-disposition',expected_state_revision=2)
    assert store.load()[0].claims['C1']['status'] == 'draft'


def test_genuine_prejournal_checkpoint_restores_then_adopts(tmp_path):
    from dd_research_runtime.checkpoints import inspect_checkpoint
    fixture=Path(__file__).parent/'fixtures'/'cycle127_checkpoint.zip'
    manifest=inspect_checkpoint(fixture)
    assert 'state_mutations' not in manifest['summary']['tables']
    path=tmp_path/'restored-127.db';restore_checkpoint(fixture,path)
    with sqlite3.connect(path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='state_mutations'").fetchone()
    store=PersistentEvidenceStore(path)
    assert store.mutation_coverage()['adoption_revision'] == 1
    apply(store,[add_claim()])
    assert store.load()[1] == 2 and store.load()[0].claims['C1']['analysis_status'] == 'advisory'


def test_assessment_bound_to_claim_version_after_updates(store):
    from dd_research_runtime.analysis_transactions import assessment_is_current
    ingest(store);apply(store,commands()[:3])
    assert assessment_is_current(store.load()[0],'A1')
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(claim='Changed bounded claim'))],operation_id='change',expected_state_revision=2)
    state,_=store.load()
    assert not assessment_is_current(state,'A1') and state.assessments['A1']['status'] == 'advisory'
    reassess=commands()[2];reassess['assessment_id']='A2'
    apply(store,[reassess],operation_id='reassess',expected_state_revision=3)
    state,_=store.load()
    assert assessment_is_current(state,'A2') and not assessment_is_current(state,'A1')


def test_repeated_claim_updates_do_not_recursively_duplicate_history(store):
    ingest(store);apply(store,[add_claim()])
    changes=[dict(type='update_claim',claim_id='C1',patch=dict(claim='Bounded revision '+str(i))) for i in range(8)]
    apply(store,changes,operation_id='revisions',expected_state_revision=2)
    history=store.load()[0].claims['C1']['belief_history']
    assert len(history) == 8
    assert all('belief_history' not in entry['previous'] for entry in history)
    assert history[-1]['previous']['claim'] == 'Bounded revision 6'
