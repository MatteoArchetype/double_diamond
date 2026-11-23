"""Double Diamond fixtures: no real participants, hardware tests or human identity."""
import copy
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_persistent_ingestion import store,ingest
from test_analysis_transactions import apply,add_claim
from test_workflow import write
from dd_research_runtime.double_diamond import transition_action,reframing_action,stage_currency
from dd_research_runtime.gate_transactions import binding
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint
from dd_research_runtime.reporting import render_markdown,report_is_current


def auth(actor,permission):return actor=='fixture-human' and permission in {'workflow_write','gate_propose','gate_decide'}


def begin(store,budget=10,snapshots=False):
    if snapshots:
        from test_persistent_ingestion import batch,auth as ingest_auth
        store.ingest(*batch(),operation_id='intake',expected_state_revision=0,expected_ledger_revision=0,authorize=ingest_auth,source_snapshots={'s1':dict(text='Exact passage s1',location='p1')})
    else:ingest(store)
    apply(store,[add_claim()])
    return write(store,dict(type='start_double_diamond',workflow_id='DD1',brief='Which interpretation is supported?',scope='Fixture only',questions=['What remains unknown?'],max_alternatives=3,max_visits=budget))


def record_for(phase):
    if phase=='discover':return dict(evidence_ids=['s1'],notes='Compare available evidence and missing perspectives',perspectives=['Publisher documentation','Affected users: not studied'],limitations='One fixture, no user interviews')
    if phase=='define':return dict(problem='A bounded interpretation problem',claim_ids=['C1'],uncertainty_ids=[],success_criteria=['Explain evidence and uncertainty'])
    if phase=='develop':return dict(alternatives=[dict(alternative_id='A'+str(i),hypothesis='Interpretation '+str(i),test='Compare with recorded evidence',claim_ids=['C1'],evidence_ids=['s1'],limitations='Fixture only') for i in range(2)])
    return dict(selected_alternative_id='A0',evaluations=[dict(evaluation_id='E1',alternative_id='A0',method='Fixture passage comparison, no experiment',evidence_ids=['s1'],outcome='inconclusive',limitations='Fixture only')],decision='stop_unresolved',summary='Uncertainty remains explicit',claim_ids=['C1'],limitations='No real-world result')


def record(store,phase,value=None,**options):return write(store,dict(type='record',phase=phase,record=record_for(phase) if value is None else value,**options))


def approve(store,action,gid):
    _,revision=store.load()
    for offset,cmd in enumerate([dict(type='propose',gate_id=gid,action=action),dict(type='decide',gate_id=gid,decision='approve',proposal_digest=binding(action))]):
        store.apply_gate(cmd,operation_id=gid+'-'+str(offset),actor='fixture-human',rationale='Simulated review',expected_state_revision=revision+offset,authorize=auth)
    return gid


def move(store,target,kind='advance',reason='Fixture learning requires this transition',gid=None):
    state,revision=store.load();gid=gid or 'G'+str(revision)
    approve(store,transition_action(state,target,reason),gid)
    return write(store,dict(type=kind,to_phase=target,reason=reason,gate_id=gid))


def deliver(store):
    begin(store)
    for phase,target in [('discover','define'),('define','develop'),('develop','deliver')]:record(store,phase);move(store,target)
    record(store,'deliver')


def finish(store,rid='R1'):
    write(store,dict(type='finish',outcome='stopped',reason='Bounded research complete with unresolved questions'))
    return write(store,dict(type='report',report_id=rid))


def test_four_phases_report_checkpoint_and_unresolved_outcome(store,tmp_path):
    deliver(store);finish(store)
    state,_=store.load();workflow=state.workflow
    assert workflow['workflow_version']==2 and workflow['status']=='stopped'
    assert [v['phase'] for v in workflow['visits']]==['discover','define','develop','deliver']
    assert all(stage_currency(state).values()) and report_is_current(state,'R1')
    text=render_markdown(state.outputs['R1'])
    assert all(name in text for name in ('Discover','Define','Develop','Deliver'))
    assert 'stop\\_unresolved' in text and store.ledger.revision()==1
    assert store.acceptance_status('R1')['structurally_ready'] is False # Legacy fixture intake retained no source snapshot.
    target=tmp_path/'saved.zip';create_checkpoint(store,target);restore_checkpoint(target,tmp_path/'restored.db')
    assert PersistentEvidenceStore(tmp_path/'restored.db').load()[0].snapshot()==state.snapshot()


def test_revisit_keeps_history_and_invalidates_downstream_work(store):
    deliver(store);original=copy.deepcopy(store.load()[0].workflow['visits'])
    move(store,'define','revisit',reason='Reconsider the framing after comparison')
    state,_=store.load()
    assert state.workflow['visits'][:4]==original and state.workflow['phase']=='define'
    assert set(state.workflow['records'])=={'discover'}
    record(store,'define');move(store,'develop');record(store,'develop');move(store,'deliver');record(store,'deliver');finish(store)
    assert len(store.load()[0].workflow['visits'])==7
    assert store.load()[0].workflow['history'][3]['kind']=='revisit'


@pytest.mark.parametrize('field',['problem','success_criteria'])
def test_exact_reframing_gate_required(store,field):
    begin(store);record(store,'discover');move(store,'define');record(store,'define');move(store,'develop')
    move(store,'define','revisit')
    changed=record_for('define');changed[field]='Reframe around the missing perspective' if field=='problem' else ['Evaluate the missing perspective']
    with pytest.raises(PermissionError):record(store,'define',changed)
    state,_=store.load();approve(store,reframing_action(state,changed),'reframe')
    wrong=dict(changed,problem='Different unapproved frame')
    with pytest.raises(PermissionError):record(store,'define',wrong,gate_id='reframe')
    record(store,'define',changed,gate_id='reframe')
    state,_=store.load();assert state.human_gates['reframe']['status']=='executed'
    assert state.workflow['visits'][1]['record']['problem']=='A bounded interpretation problem'


@pytest.mark.parametrize('kind,target',[('advance','deliver'),('revisit','develop'),('reopen','discover')])
def test_no_skips_forward_revisits_or_implicit_reopen(store,kind,target):
    begin(store);before=store.load()[0].snapshot()
    with pytest.raises((ValueError,PermissionError)):write(store,dict(type=kind,to_phase=target,reason='Fixture',gate_id='missing'))
    assert store.load()[0].snapshot()==before


def test_terminal_reopen_needs_approval_and_stales_old_report(store):
    deliver(store);finish(store)
    with pytest.raises(PermissionError):write(store,dict(type='reopen',to_phase='develop',reason='New research question',gate_id='missing'))
    move(store,'develop','reopen',reason='New evidence requires alternatives to be retested')
    state,_=store.load();assert state.workflow['status']=='active' and not report_is_current(state,'R1')
    assert state.outputs['R1']['workflow']['status']=='stopped'


def test_budget_exhaustion_requires_escalation(store):
    begin(store,budget=4)
    for _ in range(3):move(store,'discover','revisit')
    state,_=store.load()
    with pytest.raises(ValueError,match='budget exhausted'):write(store,dict(type='revisit',to_phase='discover',reason='Again',gate_id='missing'))
    write(store,dict(type='finish',outcome='escalated',reason='Visit budget exhausted; human scope decision needed'))
    assert store.load()[0].workflow['status']=='escalated'


def test_changed_evidence_use_stales_only_referenced_findings(store):
    begin(store);record(store,'discover');move(store,'define');record(store,'define')
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    state,_=store.load();assert stage_currency(state)=={'discover':True,'define':False}
    with pytest.raises(ValueError,match='revisit stale'):move(store,'develop')
    move(store,'define','revisit');record(store,'define');move(store,'develop')


def test_record_immutable_and_alternatives_diverge(store):
    begin(store);record(store,'discover')
    with pytest.raises(ValueError,match='immutable'):record(store,'discover')
    move(store,'define');record(store,'define');move(store,'develop')
    bad=record_for('develop');bad['alternatives']=bad['alternatives'][:1]
    with pytest.raises(ValueError):record(store,'develop',bad)


@pytest.mark.parametrize('change',['missing-evaluation','unknown-selection','unsupported-recommendation','no-evidence'])
def test_deliver_requires_evaluation_not_just_a_summary(store,change):
    begin(store)
    for phase,target in [('discover','define'),('define','develop'),('develop','deliver')]:record(store,phase);move(store,target)
    value=record_for('deliver')
    if change=='missing-evaluation':value['evaluations']=[]
    elif change=='unknown-selection':value['selected_alternative_id']='unknown'
    elif change=='unsupported-recommendation':value['decision']='recommend'
    else:value['evaluations'][0].update(outcome='supported',evidence_ids=[])
    with pytest.raises(ValueError):record(store,'deliver',value)


def test_revise_cannot_be_marked_finished(store):
    begin(store)
    for phase,target in [('discover','define'),('define','develop'),('develop','deliver')]:record(store,phase);move(store,target)
    value=record_for('deliver');value['decision']='revise';record(store,'deliver',value)
    with pytest.raises(ValueError,match='revise requires'):finish(store)
    move(store,'develop','revisit',reason='Evaluation inconclusive; refine competing explanations')


@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit','after_commit'])
def test_iteration_consumption_atomic_and_retryable(store,phase):
    begin(store);record(store,'discover');move(store,'define')
    reason='Fixture revisit';state,revision=store.load();approve(store,transition_action(state,'discover',reason),'return')
    revision=store.load()[1];command=dict(type='revisit',to_phase='discover',reason=reason,gate_id='return')
    def fault(name):
        if name==phase:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):write(store,command,oid='return-op',revision=revision,_fault=fault)
    reopened=PersistentEvidenceStore(store.ledger.path);assert reopened.load()[1]==revision+(phase=='after_commit')
    write(reopened,command,oid='return-op',revision=revision)
    assert len(reopened.load()[0].workflow['visits'])==3


def crash_revisit(path,revision,phase):
    def fault(name):
        if name==phase:os._exit(73)
    write(PersistentEvidenceStore(path),dict(type='revisit',to_phase='discover',reason='Fixture revisit',gate_id='return'),oid='return-op',revision=revision,_fault=fault)


@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
def test_process_death_recovery(store,phase):
    begin(store);record(store,'discover');move(store,'define');state,_=store.load()
    approve(store,transition_action(state,'discover','Fixture revisit'),'return');revision=store.load()[1]
    process=multiprocessing.get_context('spawn').Process(target=crash_revisit,args=(store.ledger.path,revision,phase));process.start();process.join(15)
    if process.is_alive():process.terminate();process.join();pytest.fail('process timeout')
    assert process.exitcode==73
    reopened=PersistentEvidenceStore(store.ledger.path);assert reopened.load()[1]==revision+(phase=='after_commit')
    write(reopened,dict(type='revisit',to_phase='discover',reason='Fixture revisit',gate_id='return'),oid='return-op',revision=revision)
    assert len(reopened.load()[0].workflow['visits'])==3


def test_approval_binds_reason_and_changed_research_content(store):
    begin(store);record(store,'discover');state,_=store.load()
    approve(store,transition_action(state,'define','Reason one'),'one')
    with pytest.raises(PermissionError):write(store,dict(type='advance',to_phase='define',reason='Reason two',gate_id='one'))
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    with pytest.raises(PermissionError):write(store,dict(type='advance',to_phase='define',reason='Reason one',gate_id='one'))
    assert store.load()[0].human_gates['one']['status']=='approved'


def test_concurrent_revisits_one_visit_commits(store):
    begin(store);record(store,'discover');move(store,'define');state,_=store.load()
    approve(store,transition_action(state,'discover','New evidence'),'return');revision=store.load()[1]
    def attempt(index):
        try:return write(store,dict(type='revisit',to_phase='discover',reason='New evidence',gate_id='return'),oid='return-write-'+str(index),revision=revision)
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert sum(r is not None for r in results)==1
    assert len(store.load()[0].workflow['visits'])==3


def test_double_diamond_acceptance_retains_host_fixture_separation(store):
    from test_acceptance import command,decide
    begin(store,snapshots=True)
    for phase,target in [('discover','define'),('define','develop'),('develop','deliver')]:record(store,phase);move(store,target)
    record(store,'deliver');finish(store)
    assert store.acceptance_status('R1')['structurally_ready']
    decide(store,command(store,mode='fixture'))
    assert store.acceptance_status('R1')['status']=='fixture_accepted'
    assert not store.acceptance_status('R1')['host_accepted']


def test_offline_learning_loop_and_existing_destination(tmp_path):
    from dd_research_runtime.dd_demo import run_demo
    result=run_demo(tmp_path/'fixture')
    assert len(result['checks'])==13 and all(result['checks'].values()) and result['mvp_ready'] is False
    text=(tmp_path/'fixture'/'research-draft.md').read_text()
    assert 'synthetic\\_only' in text and 'Iteration history' in text
    with pytest.raises(FileExistsError):run_demo(tmp_path/'fixture')


def test_learning_loop_cli_from_extracted_source():
    import subprocess
    import sys
    import json
    from pathlib import Path
    result=subprocess.run([sys.executable,'-m','dd_research_runtime.dd_demo'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
    assert result.returncode==0 and result.stderr==''
    assert all(json.loads(result.stdout)['checks'].values())


@pytest.mark.parametrize('budget',[True,3,21,4.5])
def test_invalid_visit_budget(store,budget):
    with pytest.raises(ValueError):begin(store,budget=budget)
    assert not hasattr(store.load()[0],'workflow')


def test_incomplete_or_changed_findings_cannot_finish(store):
    begin(store)
    with pytest.raises(ValueError):finish(store)
    for phase,target in [('discover','define'),('define','develop'),('develop','deliver')]:record(store,phase);move(store,target)
    record(store,'deliver')
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    with pytest.raises(ValueError):finish(store)
    write(store,dict(type='finish',outcome='escalated',reason='Changed evidence requires another research visit'))


def test_iteration_journal_tamper_fails_closed(store):
    import sqlite3
    begin(store);move(store,'discover','revisit')
    with sqlite3.connect(store.ledger.path) as db:db.execute("UPDATE state_mutations SET request='{}' WHERE operation_id=(SELECT operation_id FROM state_mutations ORDER BY revision DESC LIMIT 1)")
    with pytest.raises(ValueError,match='integrity'):store.load()
