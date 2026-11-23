"""Proposed follow-up research only; sources and identities are test fixtures."""
import copy
import json
import os
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from test_persistent_ingestion import store
from test_decision_trace import setup,save
from test_workflow import write
from test_analysis_transactions import apply
from test_double_diamond import move
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.research_agenda import inspect_agenda,read_agenda,export_agenda
from dd_research_runtime.reporting import report_is_current
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint


def prepare(store):
    setup(store);save(store)
    write(store,dict(type='finish',outcome='stopped',reason='Bounded result with an evidence gap'))
    write(store,dict(type='report',report_id='R1'))


def item(iid='follow-up',index=1):return dict(item_id=iid,criterion_index=index,evidence_gap='No independent follow-up evidence',question='Does the explanation transfer to another context?',method='desk_review',target_phase='discover',priority='high',priority_rationale='This gap prevents a recommendation',success_signal='A reviewed source from another context addresses the criterion',effort='small',depends_on=[])


def plan(store,items=None,**options):
    report=store.load()[0].outputs['R1']
    return write(store,dict(type='plan_research',agenda_id='A1',report_id='R1',report_digest=report['content_digest'],items=[item()] if items is None else items),**options)


def test_plan_preserves_report_sources_gates_and_checkpoint(store,tmp_path):
    prepare(store);before,revision=store.load();result=plan(store,oid='agenda')
    state,_=PersistentEvidenceStore(store.ledger.path).load();agenda=inspect_agenda(state,'A1')
    assert result['changed_ids']==['A1'] and agenda['current'] and agenda['status']=='proposed'
    assert agenda['items'][0]['criterion']=='State remaining uncertainty'
    assert agenda['items'][0]['evidence_origin']=='none' and not agenda['execution_authorized']
    assert state.workflow==before.workflow and state.evidence==before.evidence and state.human_gates==before.human_gates
    assert report_is_current(state,'R1') and state.outputs==before.outputs and store.ledger.revision()==1
    assert store.load_workflow_operation('agenda')['request']['command']['type']=='plan_research'
    assert plan(store,oid='agenda',revision=revision)==result
    checkpoint=tmp_path/'agenda.zip';create_checkpoint(store,checkpoint);restore_checkpoint(checkpoint,tmp_path/'restore.db')
    assert inspect_agenda(PersistentEvidenceStore(tmp_path/'restore.db').load()[0],'A1')==agenda


def test_dependency_order_respects_prerequisites_before_priority(store):
    prepare(store);first=item('first');first['priority']='low'
    second=item('second');second['depends_on']=['first']
    plan(store,[second,first]);agenda=inspect_agenda(store.load()[0],'A1')
    assert agenda['proposed_order']==['first','second']


@pytest.mark.parametrize('change',['cycle','unknown-dependency','self-dependency','duplicate-id','met-criterion','bool-criterion','empty-gap','empty-question','empty-priority-reason','empty-success-signal','unknown-method','unknown-priority','invalid-effort','deliver-target'])
def test_invalid_plans_fail_atomically(store,change):
    prepare(store);value=item();items=[value]
    if change=='cycle':
        value['depends_on']=['second'];other=item('second');other['depends_on']=['follow-up'];items.append(other)
    elif change=='unknown-dependency':value['depends_on']=['missing']
    elif change=='self-dependency':value['depends_on']=['follow-up']
    elif change=='duplicate-id':items.append(copy.deepcopy(value))
    elif change=='met-criterion':value['criterion_index']=0
    elif change=='bool-criterion':value['criterion_index']=True
    elif change=='empty-gap':value['evidence_gap']=''
    elif change=='empty-question':value['question']=''
    elif change=='empty-priority-reason':value['priority_rationale']=''
    elif change=='empty-success-signal':value['success_signal']=''
    elif change=='unknown-method':value['method']='autonomous_interview'
    elif change=='unknown-priority':value['priority']='urgent'
    elif change=='invalid-effort':value['effort']='unlimited'
    else:value['target_phase']='deliver'
    before=store.load()[0].snapshot()
    with pytest.raises(ValueError):plan(store,items)
    assert store.load()[0].snapshot()==before


@pytest.mark.parametrize('method',['interview','survey','experiment'])
def test_primary_research_planning_never_authorizes_execution(store,method):
    prepare(store);value=item();value['method']=method;plan(store,[value])
    agenda=inspect_agenda(store.load()[0],'A1')
    assert agenda['items'][0]['required_gate_types']==['primary_research']
    assert agenda['items'][0]['execution_authorized'] is False
    assert not any(gate.get('gate_type')=='primary_research' for gate in store.load()[0].human_gates.values())


def test_every_gap_covered_and_all_met_has_no_followup_requirement(store):
    setup(store)
    from test_decision_trace import delivery
    value=delivery();value['criterion_assessments'][0].update(outcome='unknown',next_research='Compare contextual evidence')
    save(store,value);write(store,dict(type='finish',outcome='stopped',reason='Two gaps'));write(store,dict(type='report',report_id='R1'))
    with pytest.raises(ValueError,match='every unmet'):plan(store)
    plan(store,[item('first',0),item('second',1)])
    assert len(store.load()[0].research_agendas['A1']['items'])==2


def test_immutable_plan_stales_after_iteration_and_requires_fresh_report(store):
    prepare(store);plan(store)
    with pytest.raises(ValueError,match='already exists'):plan(store)
    original=copy.deepcopy(store.load()[0].research_agendas['A1'])
    move(store,'discover','reopen',reason='Follow up on the missing context')
    agenda=inspect_agenda(store.load()[0],'A1')
    assert agenda['status']=='stale' and not agenda['current']
    assert store.load()[0].research_agendas['A1']==original
    report=store.load()[0].outputs['R1']
    with pytest.raises(ValueError,match='current research report'):write(store,dict(type='plan_research',agenda_id='A2',report_id='R1',report_digest=report['content_digest'],items=[item()]))


@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit','after_commit'])
def test_agenda_atomicity_and_retry(store,phase):
    prepare(store);revision=store.load()[1]
    def fault(name):
        if name==phase:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):plan(store,oid='agenda',revision=revision,_fault=fault)
    reopened=PersistentEvidenceStore(store.ledger.path);assert reopened.load()[1]==revision+(phase=='after_commit')
    plan(reopened,oid='agenda',revision=revision);assert reopened.load()[1]==revision+1


def crash_plan(path,revision,phase):
    def fault(name):
        if name==phase:os._exit(73)
    plan(PersistentEvidenceStore(path),oid='agenda',revision=revision,_fault=fault)


@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
def test_process_death_recovery(store,phase):
    prepare(store);revision=store.load()[1]
    proc=multiprocessing.get_context('spawn').Process(target=crash_plan,args=(store.ledger.path,revision,phase));proc.start();proc.join(15)
    if proc.is_alive():proc.terminate();proc.join();pytest.fail('process timeout')
    assert proc.exitcode==73
    reopened=PersistentEvidenceStore(store.ledger.path);assert reopened.load()[1]==revision+(phase=='after_commit')
    plan(reopened,oid='agenda',revision=revision);assert reopened.load()[1]==revision+1


def test_concurrent_agendas_one_revision_winner(store):
    prepare(store);revision=store.load()[1]
    def attempt(index):
        try:return plan(store,oid='agenda-'+str(index),revision=revision)
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert sum(r is not None for r in results)==1


def test_readonly_export_staleness_paths_and_markup(store,tmp_path):
    prepare(store);value=item();value['question']='<script>do not run</script> ![image](https://bad.invalid)';plan(store,[value])
    before=store.load()[0].snapshot();destination=tmp_path/'agenda.md'
    export_agenda(store.ledger.path,'A1',destination)
    text=destination.read_text();assert '<script>' not in text and '![image]' not in text and 'Planning only' in text
    assert store.load()[0].snapshot()==before
    with pytest.raises(FileExistsError):export_agenda(store.ledger.path,'A1',destination)
    link=tmp_path/'link.md';link.symlink_to(destination)
    with pytest.raises(FileExistsError):export_agenda(store.ledger.path,'A1',link)
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    with pytest.raises(ValueError,match='stale'):export_agenda(store.ledger.path,'A1',tmp_path/'stale.md')
    export_agenda(store.ledger.path,'A1',tmp_path/'historical.json',format='json',allow_stale=True)
    assert json.loads((tmp_path/'historical.json').read_text())['status']=='stale'


def test_cli_missing_database_never_creates_it(tmp_path):
    import subprocess
    import sys
    missing=tmp_path/'missing.db'
    result=subprocess.run([sys.executable,'-m','dd_research_runtime.agenda_cli','inspect',str(missing),'A1'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=15)
    assert result.returncode==1 and not missing.exists()


def test_changed_request_unauthorized_and_no_gate_bypass(store):
    prepare(store);revision=store.load()[1];plan(store,oid='agenda',revision=revision)
    value=item();value['question']='Changed question'
    with pytest.raises(ValueError):plan(store,[value],oid='agenda',revision=revision)
    request=store.load_workflow_operation('agenda')['request']
    with pytest.raises(PermissionError):store.apply_workflow(request['command'],operation_id='agenda',actor=request['actor'],rationale=request['rationale'],expected_state_revision=revision,authorize=lambda *args:False)
    assert len(store.load()[0].research_agendas)==1


def test_all_met_criteria_do_not_create_artificial_evidence_gaps(store):
    from test_decision_trace import delivery
    setup(store);value=delivery();value['criterion_assessments'][1].update(outcome='met',evaluation_ids=['E1'],rationale='Supported fixture assessment',next_research='')
    save(store,value);write(store,dict(type='finish',outcome='stopped',reason='Fixture criteria addressed'));write(store,dict(type='report',report_id='R1'))
    with pytest.raises(ValueError,match='no unmet'):plan(store)


@pytest.mark.parametrize('count',[0,21])
def test_research_agenda_item_budget(store,count):
    prepare(store)
    with pytest.raises(ValueError,match='1 to 20'):plan(store,[item(str(i)) for i in range(count)])


def test_report_digest_binding_and_journal_tamper(store):
    import sqlite3
    prepare(store)
    with pytest.raises(ValueError,match='report digest'):write(store,dict(type='plan_research',agenda_id='A1',report_id='R1',report_digest='wrong',items=[item()]))
    plan(store,oid='agenda')
    with sqlite3.connect(store.ledger.path) as db:db.execute("UPDATE state_mutations SET request='{}' WHERE operation_id='agenda'")
    with pytest.raises(ValueError,match='integrity'):store.load()


def test_agenda_learning_example_and_cli(tmp_path):
    import subprocess
    import sys
    from dd_research_runtime.agenda_demo import run_demo
    result=run_demo(tmp_path/'example')
    assert len(result['checks'])==9 and all(result['checks'].values()) and result['mvp_ready'] is False
    assert 'transfer' in (tmp_path/'example'/'research-agenda.md').read_text()
    output=tmp_path/'cli-agenda.md'
    process=subprocess.run([sys.executable,'-m','dd_research_runtime.agenda_cli','export',str(tmp_path/'example'/'research.sqlite'),'follow-up-agenda',str(output)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=20)
    assert process.returncode==0 and json.loads(process.stdout)['execution_authorized'] is False and output.is_file()
    with pytest.raises(FileExistsError):run_demo(tmp_path/'example')


def test_genuine_cycle133_report_is_unchanged_without_agenda(tmp_path):
    fixture=Path(__file__).parent/'fixtures'/'cycle133_criteria_checkpoint.zip'
    restore_checkpoint(fixture,tmp_path/'cycle133.db')
    state,_=PersistentEvidenceStore(tmp_path/'cycle133.db').load()
    assert state.workflow['workflow_version']==3 and state.outputs['after-iteration']['decision_trace']
    assert not getattr(state,'research_agendas',{}) and report_is_current(state,'after-iteration')


def test_gate_activity_does_not_change_research_plan_or_authorize_it(store):
    from test_double_diamond import approve
    prepare(store);plan(store)
    approve(store,dict(type='gated_action',action='primary_research',payload=dict(scope='Fixture only; no external execution')),'separate-primary-review')
    agenda=inspect_agenda(store.load()[0],'A1')
    assert agenda['current'] is True and agenda['basis_report_current'] is False
    assert agenda['execution_authorized'] is False and all(i['execution_authorized'] is False for i in agenda['items'])
