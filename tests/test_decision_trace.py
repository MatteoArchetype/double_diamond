"""Criterion-linked research decisions; all people and source records are fixtures."""
import copy
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_persistent_ingestion import store,ingest
from test_analysis_transactions import apply,add_claim
from test_workflow import write
from test_double_diamond import move,record_for,approve
from dd_research_runtime.double_diamond import decision_trace,reframing_action
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.reporting import render_markdown
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint


def setup(store, *, additional_evidence=False):
    ingest(store)
    if additional_evidence:
        ingest(store,'s2',expected_state_revision=1,expected_ledger_revision=1)
    apply(store,[add_claim()],expected_state_revision=2 if additional_evidence else 1)
    write(store,dict(type='start_criteria_research',workflow_id='DD-criteria',brief='Compare options against stated success criteria',scope='Fixture only',questions=['Which criteria are supported?'],max_alternatives=2,max_visits=10))
    for phase,target in [('discover','define'),('define','develop'),('develop','deliver')]:
        record=record_for(phase)
        if phase=='define':record['success_criteria']=['Bound the explanation','State remaining uncertainty']
        write(store,dict(type='record',phase=phase,record=record));move(store,target)


def delivery():
    record=record_for('deliver')
    record['evaluations'][0]['outcome']='supported'
    record['criterion_assessments']=[dict(criterion_index=0,outcome='met',evaluation_ids=['E1'],rationale='Fixture passage supports a bounded description',next_research=''),
        dict(criterion_index=1,outcome='unknown',evaluation_ids=[],rationale='No independent follow-up evidence',next_research='Seek an additional source and compare the explanation')]
    return record


def save(store,record=None,**options):return write(store,dict(type='record',phase='deliver',record=delivery() if record is None else record),**options)


def test_mixed_outcomes_trace_report_and_checkpoint(store,tmp_path):
    setup(store);save(store)
    write(store,dict(type='finish',outcome='stopped',reason='Bounded research leaves the second criterion unknown'))
    write(store,dict(type='report',report_id='R1'))
    state,_=store.load();trace=decision_trace(state)
    assert trace['all_criteria_met'] is False and [r['outcome'] for r in trace['criteria']]==['met','unknown']
    assert trace['criteria'][0]['evidence_ids']==['s1'] and trace['criteria'][1]['evidence_origin']=='none'
    assert trace==state.outputs['R1']['decision_trace']
    text=render_markdown(state.outputs['R1']);assert 'Decision against success criteria' in text and 'Seek an additional source' in text
    path=tmp_path/'saved.zip';create_checkpoint(store,path);restore_checkpoint(path,tmp_path/'restored.db')
    assert PersistentEvidenceStore(tmp_path/'restored.db').load()[0].snapshot()==state.snapshot()


@pytest.mark.parametrize('change',['missing','duplicate','out-of-range','boolean-index','unknown-evaluation','wrong-alternative','no-reason','no-next-research','unsupported-met','supported-not-met','unknown-outcome','recommend-with-gap'])
def test_invalid_criterion_assessments_fail_without_partial_write(store,change):
    setup(store);value=delivery()
    if change=='missing':value['criterion_assessments'].pop()
    elif change=='duplicate':value['criterion_assessments'][1]['criterion_index']=0
    elif change=='out-of-range':value['criterion_assessments'][1]['criterion_index']=2
    elif change=='boolean-index':value['criterion_assessments'][1]['criterion_index']=True
    elif change=='unknown-evaluation':value['criterion_assessments'][0]['evaluation_ids']=['missing']
    elif change=='wrong-alternative':value['evaluations'][0]['alternative_id']='A1'
    elif change=='no-reason':value['criterion_assessments'][0]['rationale']=''
    elif change=='no-next-research':value['criterion_assessments'][1]['next_research']=''
    elif change=='unsupported-met':value['evaluations'][0]['outcome']='unsupported'
    elif change=='supported-not-met':value['criterion_assessments'][0].update(outcome='not_met',next_research='Retest')
    elif change=='unknown-outcome':value['criterion_assessments'][0]['outcome']='good'
    else:value['decision']='recommend'
    before=store.load()[0].snapshot()
    with pytest.raises(ValueError):save(store,value)
    assert store.load()[0].snapshot()==before


def test_all_criteria_met_allows_recorded_recommendation(store):
    setup(store);value=delivery();value['decision']='recommend'
    value['criterion_assessments'][1].update(outcome='met',evaluation_ids=['E1'],rationale='Fixture evaluation also addresses the second criterion',next_research='')
    save(store,value)
    assert decision_trace(store.load()[0])['all_criteria_met'] is True


def test_failed_criterion_links_unsupported_evidence_and_next_research(store):
    setup(store);value=delivery();value['evaluations'][0]['outcome']='unsupported'
    value['criterion_assessments'][0].update(outcome='not_met',next_research='Return to Develop and refine the explanation')
    save(store,value);trace=decision_trace(store.load()[0])
    assert trace['criteria'][0]['outcome']=='not_met' and trace['criteria'][0]['evidence_ids']==['s1']


def test_criteria_revision_requires_gate_and_reassessment(store):
    setup(store);save(store);original=copy.deepcopy(store.load()[0].workflow['visits'][-1])
    move(store,'define','revisit',reason='The success criteria need refinement')
    value=record_for('define');value['success_criteria']=['A revised criterion']
    with pytest.raises(PermissionError):write(store,dict(type='record',phase='define',record=value))
    approve(store,reframing_action(store.load()[0],value),'new-frame')
    write(store,dict(type='record',phase='define',record=value,gate_id='new-frame'))
    move(store,'develop');write(store,dict(type='record',phase='develop',record=record_for('develop')));move(store,'deliver')
    with pytest.raises(ValueError):save(store,delivery())
    assert store.load()[0].workflow['visits'][3]==original


@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit','after_commit'])
def test_assessment_atomicity_retry(store,phase):
    setup(store);revision=store.load()[1];value=delivery()
    def fault(name):
        if name==phase:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):save(store,value,oid='criteria-record',revision=revision,_fault=fault)
    reopened=PersistentEvidenceStore(store.ledger.path);assert reopened.load()[1]==revision+(phase=='after_commit')
    save(reopened,value,oid='criteria-record',revision=revision)
    assert reopened.load()[1]==revision+1


def crash_save(path,revision,phase):
    def fault(name):
        if name==phase:os._exit(73)
    save(PersistentEvidenceStore(path),oid='criteria-record',revision=revision,_fault=fault)


@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
def test_process_death_recovery(store,phase):
    setup(store);revision=store.load()[1]
    proc=multiprocessing.get_context('spawn').Process(target=crash_save,args=(store.ledger.path,revision,phase));proc.start();proc.join(15)
    if proc.is_alive():proc.terminate();proc.join();pytest.fail('process timeout')
    assert proc.exitcode==73
    reopened=PersistentEvidenceStore(store.ledger.path);assert reopened.load()[1]==revision+(phase=='after_commit')
    save(reopened,oid='criteria-record',revision=revision);assert reopened.load()[1]==revision+1


def test_concurrent_assessments_only_one_commits(store):
    setup(store);revision=store.load()[1]
    def attempt(index):
        try:return save(store,oid='criteria-record-'+str(index),revision=revision)
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert sum(r is not None for r in results)==1
    assert store.load()[1]==revision+1


def test_genuine_cycle132_checkpoint_preserves_report_hashes(tmp_path):
    from pathlib import Path
    fixture=Path(__file__).parent/'fixtures'/'cycle132_double_diamond_checkpoint.zip'
    restore_checkpoint(fixture,tmp_path/'cycle132.db')
    state,_=PersistentEvidenceStore(tmp_path/'cycle132.db').load()
    assert state.workflow['workflow_version']==2
    assert 'decision_trace' not in state.outputs['after-iteration']
    assert len(state.workflow['visits'])==7
    assert state.outputs['after-iteration']['status']=='draft'


def test_criteria_fixture_reports_specific_research_actions(tmp_path):
    from dd_research_runtime.criteria_demo import run_demo
    result=run_demo(tmp_path/'criteria')
    assert len(result['checks'])==16 and all(result['checks'].values()) and result['mvp_ready'] is False
    text=(tmp_path/'criteria'/'research-draft.md').read_text()
    assert 'Acquire an independently reviewed contextual observation' in text
    assert 'Test the explanation in a different context' in text
    assert 'synthetic\\_only' in text


def test_report_retains_evaluation_only_evidence_without_rewriting_legacy_reports(store,tmp_path):
    setup(store,additional_evidence=True)
    record=delivery()
    record['evaluations'][0]['evidence_ids']=['s1','s2']
    save(store,record)
    write(store,dict(type='finish',outcome='stopped',reason='Retain evidence for review'))
    write(store,dict(type='report',report_id='legacy'))
    legacy=store.load()[0].outputs['legacy']
    assert 'evaluation_evidence' not in legacy
    write(store,dict(type='report',report_id='traceable',include_evaluation_evidence=True))
    state,_=store.load()
    assert state.outputs['legacy']==legacy
    report=state.outputs['traceable']
    item,=report['evaluation_evidence']
    assert item['evidence_id']=='s2'
    assert item['evidence']==state.evidence['s2']
    assert item['source']==state.sources['s2']
    assert 'Exact passage s2' in render_markdown(report)
    path=tmp_path/'report.zip'
    create_checkpoint(store,path)
    restore_checkpoint(path,tmp_path/'restored-report.db')
    restored,_=PersistentEvidenceStore(tmp_path/'restored-report.db').load()
    assert restored.outputs==state.outputs
