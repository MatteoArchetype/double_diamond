"""All reviewers, host callbacks and sources here are simulated test fixtures."""
import copy
import json
import os
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_persistent_ingestion import store,batch,auth as ingestion_auth
from test_analysis_transactions import apply,add_claim
from test_workflow import start,advance,record,alternatives,write
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint
from dd_research_runtime.reporting import report_is_current


def auth(actor,permission):return actor=='simulated-host' and permission in {'acceptance_record','acceptance_confirm_real_sources'}


def make_case(store,*,snapshots=True,synthetic=False):
    sid='synthetic-s1' if synthetic else 's1'
    validation,review=batch(sid,synthetic=synthetic)
    kwargs={'source_snapshots':{sid:dict(text='Exact passage '+sid,location='p1')}} if snapshots else {}
    store.ingest(validation,review,operation_id='intake',expected_state_revision=0,expected_ledger_revision=0,authorize=ingestion_auth,**kwargs)
    claim=add_claim();claim['record']['evidence_ids']=[sid]
    apply(store,[claim]);start(store);advance(store,'discovery');record(store,'discovery',dict(evidence_ids=[sid],notes='Simulated source review'))
    advance(store,'definition');record(store,'definition',dict(problem='Simulated case',claim_ids=['C1'],uncertainty_ids=[]))
    advance(store,'alternatives');data=alternatives()
    for alternative in data['alternatives']:alternative['evidence_ids']=[sid]
    record(store,'alternatives',data);advance(store,'synthesis')
    record(store,'synthesis',dict(summary='Simulated bounded summary',claim_ids=['C1'],limitations='Test fixtures, not real-source acceptance'))
    write(store,dict(type='finish',outcome='stopped',reason='Fixture bounded case'));write(store,dict(type='report',report_id='R1'))


def command(store,*,mode='fixture',decision='accept',aid='A1'):
    status=store.acceptance_status('R1')
    attestations=[]
    if decision=='accept':
        for source in status['source_bindings']:
            attestations.append({**{k:source[k] for k in ('evidence_id','ingestion_operation_id','snapshot_digest','source_url')},
                'acquired_at':'2026-01-01T00:00:00+00:00','acquisition_method':'Simulated fixture acquisition',
                'independence_basis':'Simulated test attestation; not independent real-world verification'})
    return dict(type='decide',acceptance_id=aid,report_id='R1',report_digest=status['report_digest'],decision=decision,review_mode=mode,
                source_attestations=attestations,limitations=['Simulated test case only'])


def decide(store,cmd=None,**options):
    args=dict(operation_id='acceptance-1',actor='simulated-host',rationale='Simulated decision, not actual human acceptance',expected_state_revision=store.load()[1],authorize=auth)
    args.update(options)
    return store.apply_acceptance(command(store) if cmd is None else cmd,**args)


def test_fixture_acceptance_never_marks_host_accepted(store,tmp_path):
    make_case(store);before,revision=store.load();cmd=command(store);result=decide(store,cmd)
    status=store.acceptance_status('R1');state,_=store.load()
    assert status['status']=='fixture_accepted' and status['host_accepted'] is False
    assert status['software_release_certified'] is False and status['publication_authorized'] is False
    assert report_is_current(state,'R1') and state.evidence==before.evidence and state.sources==before.sources
    assert state.workflow==before.workflow and store.ledger.revision()==1
    assert decide(store,cmd,expected_state_revision=revision)==result
    assert store.mutation_coverage()['acceptance_mutations']==1
    audit=store.load_acceptance_operation('acceptance-1');assert audit['request']['command']==cmd and len(audit['entry_hash'])==64
    checkpoint=tmp_path/'accepted.zip';create_checkpoint(store,checkpoint);restore_checkpoint(checkpoint,tmp_path/'restored.db')
    reopened=PersistentEvidenceStore(tmp_path/'restored.db')
    assert reopened.acceptance_status('R1')==status and reopened.load()[0].snapshot()==state.snapshot()


def test_simulated_host_mode_status_requires_extra_permission(store):
    make_case(store);cmd=command(store,mode='host');before=store.load()[1]
    with pytest.raises(PermissionError):decide(store,cmd,authorize=lambda actor,p:p=='acceptance_record')
    assert store.load()[1]==before
    decide(store,cmd)
    status=store.acceptance_status('R1');assert status['status']=='host_accepted' and status['host_accepted']
    assert status['software_release_certified'] is False
    # This callback exercises host mode in a unit test; it is not real authentication.


@pytest.mark.parametrize('kwargs,blocker',[(dict(snapshots=False),'retained_real_source_snapshots_required'),(dict(synthetic=True),'real_source_evidence_required')])
def test_missing_retention_and_synthetic_only_fail_closed(store,kwargs,blocker):
    make_case(store,**kwargs);status=store.acceptance_status('R1')
    assert blocker in status['blockers'] and not status['structurally_ready']
    with pytest.raises(ValueError,match='case not ready'):decide(store,command(store,mode='host'))
    assert not getattr(store.load()[0],'acceptance_records',{})


@pytest.mark.parametrize('field,value',[('snapshot_digest','wrong'),('ingestion_operation_id','wrong'),('source_url','https://wrong.invalid'),('acquired_at','2099-01-01T00:00:00+00:00'),('acquired_at','2026-01-01'),('acquisition_method',''),('independence_basis','')])
def test_snapshot_attestation_binding(store,field,value):
    make_case(store);cmd=command(store);cmd['source_attestations'][0][field]=value
    with pytest.raises(ValueError):decide(store,cmd)
    assert store.acceptance_status('R1')['status']=='pending_human_review'


def test_attestations_complete_unique_and_report_exact(store):
    make_case(store)
    for modifier in ('missing','duplicate','wrong-report','no-limitations'):
        cmd=command(store)
        if modifier=='missing':cmd['source_attestations']=[]
        elif modifier=='duplicate':cmd['source_attestations']*=2
        elif modifier=='wrong-report':cmd['report_digest']='wrong'
        else:cmd['limitations']=[]
        with pytest.raises(ValueError):decide(store,cmd)


def test_append_only_reject_accept_and_latest_sequence(store):
    make_case(store)
    decide(store,command(store,decision='reject',aid='Z-reject'))
    assert store.acceptance_status('R1')['status']=='rejected'
    decide(store,command(store,mode='host',aid='A-accept'),operation_id='acceptance-2')
    assert PersistentEvidenceStore(store.ledger.path).acceptance_status('R1')['status']=='host_accepted'
    decide(store,command(store,decision='reject',aid='B-reject'),operation_id='acceptance-3')
    assert store.acceptance_status('R1')['status']=='rejected'
    assert len(store.load()[0].acceptance_records)==3


def test_research_change_stales_acceptance_without_erasing_history(store):
    make_case(store);decide(store,command(store,mode='host'))
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    status=store.acceptance_status('R1')
    assert status['status']=='stale' and not status['host_accepted']
    assert status['latest_decision']['status']=='host_accepted'
    with pytest.raises(ValueError,match='current report'):decide(store,command(store,aid='A2'),operation_id='acceptance-2')


@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit','after_commit'])
def test_acceptance_atomicity_and_idempotent_recovery(store,phase):
    make_case(store);cmd=command(store);before=store.load()[1]
    def fault(name):
        if name==phase:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):decide(store,cmd,expected_state_revision=before,_fault=fault)
    reopened=PersistentEvidenceStore(store.ledger.path)
    assert reopened.load()[1]==before+(phase=='after_commit')
    decide(reopened,cmd,expected_state_revision=before)
    assert reopened.load()[1]==before+1


def crash_acceptance(path,cmd,phase,revision):
    def fault(name):
        if name==phase:os._exit(73)
    decide(PersistentEvidenceStore(path),cmd,expected_state_revision=revision,_fault=fault)


@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
def test_process_termination_recovery(store,phase):
    make_case(store);cmd=command(store);revision=store.load()[1]
    proc=multiprocessing.get_context('spawn').Process(target=crash_acceptance,args=(store.ledger.path,cmd,phase,revision))
    proc.start();proc.join(15)
    if proc.is_alive():proc.terminate();proc.join();pytest.fail('child timeout')
    assert proc.exitcode==73
    reopened=PersistentEvidenceStore(store.ledger.path);assert reopened.load()[1]==revision+(phase=='after_commit')
    decide(reopened,cmd,expected_state_revision=revision);assert reopened.load()[1]==revision+1


def test_concurrent_conflicting_decisions_one_winner(store):
    make_case(store);revision=store.load()[1];commands=[command(store),command(store,decision='reject',aid='A2')]
    def attempt(index):
        try:return decide(store,commands[index],operation_id='acceptance-'+str(index),expected_state_revision=revision)
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert sum(result is not None for result in results)==1
    assert len(store.load()[0].acceptance_records)==1


@pytest.mark.parametrize('callback',[None,lambda *args:1,lambda *args:False])
def test_authorization_required_for_writes_and_retries(store,callback):
    make_case(store);cmd=command(store);decide(store,cmd)
    with pytest.raises(PermissionError):decide(store,cmd,authorize=callback)
    assert len(store.load()[0].acceptance_records)==1


def test_operation_ids_global_and_no_overwrite(store):
    make_case(store);cmd=command(store);decide(store,cmd)
    with pytest.raises(ValueError):decide(store,command(store,aid='other'))
    with pytest.raises(ValueError):decide(store,cmd,operation_id='intake')
    with pytest.raises(ValueError):write(store,dict(type='report',report_id='R2'),oid='acceptance-1')
    with pytest.raises(KeyError):store.load_acceptance_operation('unknown')


def test_readonly_cli_inspection_and_missing_database(store,tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    from dd_research_runtime.acceptance_cli import inspect_acceptance
    make_case(store);before=store.load()[0].snapshot()
    status=inspect_acceptance(store.ledger.path,'R1')
    assert status['structurally_ready'] and status['status']=='pending_human_review'
    assert store.load()[0].snapshot()==before
    root=Path(__file__).resolve().parents[1];missing=tmp_path/'missing.db'
    result=subprocess.run([sys.executable,'-m','dd_research_runtime.acceptance_cli','inspect',str(missing),'R1'],cwd=root,capture_output=True,text=True,timeout=15)
    assert result.returncode==1 and not missing.exists()
    assert json.loads(result.stderr)['ok'] is False


def test_rejected_does_not_assert_source_verification(store):
    make_case(store);cmd=command(store,decision='reject');cmd['source_attestations']=[dict(fake=True)]
    with pytest.raises(ValueError,match='must not assert'):decide(store,cmd)


def test_stale_stage_and_escalated_case_cannot_accept(store):
    make_case(store)
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='later',expected_state_revision=store.load()[1])
    write(store,dict(type='report',report_id='R2'))
    status=store.acceptance_status('R2');assert 'current_stage_records_required' in status['blockers']
    cmd=command(store);cmd.update(report_id='R2',report_digest=status['report_digest'])
    with pytest.raises(ValueError,match='case not ready'):decide(store,cmd)


def test_acceptance_tamper_replay_fails_closed(store):
    import sqlite3
    make_case(store);decide(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute("UPDATE state_mutations SET request='{}' WHERE kind='acceptance'")
    with pytest.raises(ValueError,match='integrity'):store.load()
