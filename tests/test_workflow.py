import copy
import json
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_persistent_ingestion import store,ingest
from test_analysis_transactions import apply,add_claim
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.workflow import transition_action,domain_digest
from dd_research_runtime.gate_transactions import binding
from dd_research_runtime.reporting import report_is_current,render_markdown
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint


def auth(actor,permission):return actor=='fixture-human' and permission in {'workflow_write','gate_propose','gate_decide'}


def write(store,command,oid=None,revision=None,**options):
    if revision is None:revision=store.load()[1]
    return store.apply_workflow(command,operation_id=oid or 'workflow-'+str(revision),actor='fixture-human',rationale='Fixture workflow',expected_state_revision=revision,authorize=auth,**options)


def start(store):return write(store,dict(type='start',workflow_id='W1',brief='Fixture decision question',scope='Fixture only',questions=['What is supported within this fixture?'],max_alternatives=3))


def approve_transition(store,target,gid=None):
    state,rev=store.load();gid=gid or 'to-'+target;action=transition_action(state,target)
    def gate(command,oid,revision):return store.apply_gate(command,operation_id=oid,actor='fixture-human',rationale='Simulated human review',expected_state_revision=revision,authorize=auth)
    gate(dict(type='propose',gate_id=gid,action=action),gid+'-proposal',rev)
    gate(dict(type='decide',gate_id=gid,decision='approve',proposal_digest=binding(action)),gid+'-decision',rev+1)
    return gid


def advance(store,target):return write(store,dict(type='advance',to_phase=target,gate_id=approve_transition(store,target)))


def record(store,phase,value):return write(store,dict(type='record',phase=phase,record=value))


def alternatives():
    return dict(alternatives=[dict(alternative_id='A'+str(i),hypothesis='Fixture interpretation '+str(i),test='Compare recorded fixture passage',outcome='inconclusive',claim_ids=['C1'],evidence_ids=['s1'],limitations='Synthetic demonstration, no independent experiment') for i in range(2)])


def complete(store):
    ingest(store);apply(store,[add_claim()]);start(store)
    advance(store,'discovery');record(store,'discovery',dict(evidence_ids=['s1'],notes='Reviewed fixture passage'))
    advance(store,'definition');record(store,'definition',dict(problem='Bounded fixture problem',claim_ids=['C1'],uncertainty_ids=[]))
    advance(store,'alternatives');record(store,'alternatives',alternatives())
    advance(store,'synthesis');record(store,'synthesis',dict(summary='Fixture remains inconclusive',claim_ids=['C1'],limitations='One fixture passage; no real-world inference'))
    write(store,dict(type='finish',outcome='stopped',reason='Bound reached; remaining uncertainty stated'))
    return write(store,dict(type='report',report_id='R1'))


def test_full_workflow_report_checkpoint(store,tmp_path):
    result=complete(store);state,revision=PersistentEvidenceStore(store.ledger.path).load()
    assert result['state_revision']==revision and state.workflow['status']=='stopped'
    assert len(state.workflow['history'])==4 and set(state.workflow['records'])=={'discovery','definition','alternatives','synthesis'}
    report=state.outputs['R1'];item=report['claims'][0]['evidence'][0]
    assert item['evidence']['finding']=='Exact passage s1' and item['evidence']['exact_location']=='p1'
    assert item['source']['url']=='https://example.org/s1' and not item['synthetic']
    assert report['publication_authorized'] is False and report_is_current(state,'R1')
    assert 'DRAFT' in render_markdown(report) and 'stopped' in render_markdown(report)
    assert store.ledger.revision()==1 and store.mutation_coverage()['workflow_mutations']==11
    target=tmp_path/'saved.zip';create_checkpoint(store,target);restore_checkpoint(target,tmp_path/'restore.db')
    assert PersistentEvidenceStore(tmp_path/'restore.db').load()[0].snapshot()==state.snapshot()


@pytest.mark.parametrize('command',[
    dict(type='advance',to_phase='synthesis',gate_id='missing'),
    dict(type='advance',to_phase='discovery',gate_id='missing'),
    dict(type='record',phase='definition',record={}),
    dict(type='report',report_id='R1'),dict(type='finish',outcome='stopped',reason='too soon'),
])
def test_no_skip_unapproved_or_premature_completion(store,command):
    start(store);before=store.load()[0].snapshot()
    with pytest.raises((ValueError,PermissionError)):write(store,command)
    assert store.load()[0].snapshot()==before


def test_stale_content_invalidates_approved_transition(store):
    ingest(store);apply(store,[add_claim()]);start(store);gid=approve_transition(store,'discovery')
    revision=store.load()[1]
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=revision)
    with pytest.raises(PermissionError):write(store,dict(type='advance',to_phase='discovery',gate_id=gid))
    assert store.load()[0].workflow['phase']=='brief'


def test_early_escalation_is_explicit_and_terminal(store):
    start(store);write(store,dict(type='finish',outcome='escalated',reason='Missing authenticated source review'))
    write(store,dict(type='report',report_id='escalation'))
    state,_=store.load();assert state.outputs['escalation']['workflow']['status']=='escalated'
    with pytest.raises(ValueError):write(store,dict(type='advance',to_phase='discovery',gate_id='x'))


def test_report_staleness_after_analysis(store):
    complete(store);revision=store.load()[1]
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='unknown'))],operation_id='later',expected_state_revision=revision)
    state,_=store.load();assert not report_is_current(state,'R1')
    write(store,dict(type='report',report_id='R2'))
    assert report_is_current(store.load()[0],'R2')


@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit','after_commit'])
def test_transition_atomicity_and_lost_response(store,phase):
    start(store);gid=approve_transition(store,'discovery');before=store.load()[1]
    command=dict(type='advance',to_phase='discovery',gate_id=gid)
    def fault(name):
        if name==phase:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):write(store,command,oid='advance',revision=before,_fault=fault)
    reopened=PersistentEvidenceStore(store.ledger.path);state,revision=reopened.load()
    assert revision==before+(phase=='after_commit')
    assert state.workflow['phase']==('discovery' if phase=='after_commit' else 'brief')
    assert state.human_gates[gid]['status']==('executed' if phase=='after_commit' else 'approved')
    write(reopened,command,oid='advance',revision=before)
    assert reopened.load()[1]==before+1


def crash_transition(path,phase,revision):
    def fault(name):
        if name==phase:os._exit(73)
    write(PersistentEvidenceStore(path),dict(type='advance',to_phase='discovery',gate_id='to-discovery'),oid='advance',revision=revision,_fault=fault)


@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
def test_process_death_recovery(store,phase):
    start(store);approve_transition(store,'discovery');before=store.load()[1]
    proc=multiprocessing.get_context('spawn').Process(target=crash_transition,args=(store.ledger.path,phase,before))
    proc.start();proc.join(15)
    if proc.is_alive():proc.terminate();proc.join();pytest.fail('process timeout')
    assert proc.exitcode==73
    reopened=PersistentEvidenceStore(store.ledger.path)
    assert reopened.load()[1]==before+(phase=='after_commit')
    write(reopened,dict(type='advance',to_phase='discovery',gate_id='to-discovery'),oid='advance',revision=before)
    assert reopened.load()[0].workflow['phase']=='discovery'


def test_concurrent_transition_one_commit(store):
    start(store);approve_transition(store,'discovery');revision=store.load()[1]
    def attempt(index):
        try:return write(store,dict(type='advance',to_phase='discovery',gate_id='to-discovery'),oid='advance-'+str(index),revision=revision)
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert sum(r is not None for r in results)==1
    assert store.load()[1]==revision+1


@pytest.mark.parametrize('callback',[None,lambda *args:1,lambda *args:False])
def test_host_authorization_required(store,callback):
    with pytest.raises(PermissionError):store.apply_workflow(dict(type='finish',outcome='escalated',reason='test'),operation_id='x',actor='human',rationale='Test',expected_state_revision=0,authorize=callback)
    assert store.load()[1]==0


def test_alternative_limits_and_missing_refs(store):
    ingest(store);apply(store,[add_claim()]);start(store);advance(store,'discovery')
    with pytest.raises(ValueError):record(store,'discovery',dict(evidence_ids=['unknown'],notes='bad'))
    record(store,'discovery',dict(evidence_ids=['s1'],notes='Fixture'));advance(store,'definition')
    record(store,'definition',dict(problem='Fixture',claim_ids=['C1'],uncertainty_ids=[]));advance(store,'alternatives')
    for count in (0,1,4):
        data=alternatives();data['alternatives']=[dict(data['alternatives'][0],alternative_id=str(i)) for i in range(count)]
        with pytest.raises(ValueError):record(store,'alternatives',data)
    data=alternatives();data['alternatives'][0].update(outcome='supported',evidence_ids=[])
    with pytest.raises(ValueError):record(store,'alternatives',data)


def test_report_escapes_markup(store):
    complete(store);r=copy.deepcopy(store.load()[0].outputs['R1']);r['brief']={'text':'<script>alert(1)</script> `danger`\n# Fake header'}
    rendered=render_markdown(r)
    assert '<script>' not in rendered and '`danger`' not in rendered and '\n# Fake header' not in rendered


def test_export_existing_snapshot_no_overwrite_and_staleness(store,tmp_path):
    from dd_research_runtime.reporting import export_report
    complete(store);before=store.load()[0].snapshot()
    destination=tmp_path/'draft.md';export_report(store.ledger.path,'R1',destination)
    assert 'Exact passage s1' in destination.read_text() and store.load()[0].snapshot()==before
    with pytest.raises(FileExistsError):export_report(store.ledger.path,'R1',destination)
    link=tmp_path/'link.md';link.symlink_to(destination)
    with pytest.raises(FileExistsError):export_report(store.ledger.path,'R1',link)
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    with pytest.raises(ValueError,match='stale'):export_report(store.ledger.path,'R1',tmp_path/'stale.md')
    assert not (tmp_path/'stale.md').exists()
    export_report(store.ledger.path,'R1',tmp_path/'explicit.md',allow_stale=True)
    assert (tmp_path/'explicit.md').read_text().startswith('STALE DRAFT')
    export_report(store.ledger.path,'R1',tmp_path/'explicit.json',format='json',allow_stale=True)
    assert json.loads((tmp_path/'explicit.json').read_text())['current_at_export'] is False


def test_export_cli_missing_source_and_saved_report(store,tmp_path):
    import subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1];missing=tmp_path/'missing.db';destination=tmp_path/'draft.md'
    args=[sys.executable,'-m','dd_research_runtime.report_cli']
    result=subprocess.run(args+[str(missing),'R1',str(destination)],cwd=root,capture_output=True,text=True,timeout=15)
    assert result.returncode==1 and not missing.exists() and not destination.exists()
    complete(store)
    result=subprocess.run(args+[str(store.ledger.path),'R1',str(destination)],cwd=root,capture_output=True,text=True,timeout=15)
    assert result.returncode==0 and json.loads(result.stdout)['status']=='draft'
    assert destination.is_file()


def test_report_retains_synthetic_mixed_and_stale_assessments(store):
    from test_persistent_ingestion import batch,auth as ingest_auth
    from assessment import DIMENSIONS
    ingest(store)
    store.ingest(*batch('synthetic-fixture',synthetic=True),operation_id='synthetic',expected_state_revision=1,expected_ledger_revision=1,authorize=ingest_auth)
    claim=add_claim();claim['record']['evidence_ids']=['s1','synthetic-fixture']
    apply(store,[claim,dict(type='assess_evidence',assessment_id='A1',evidence_id='s1',claim_id='C1',dimensions={d:'unknown' for d in DIMENSIONS},limitations=['Fixture only'],rationale='Fixture assessment')],expected_state_revision=2)
    start(store);write(store,dict(type='finish',outcome='escalated',reason='Insufficient real-source verification'))
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    write(store,dict(type='report',report_id='mixed'))
    report=store.load()[0].outputs['mixed']
    assert report['claims'][0]['evidence_origin']=='mixed'
    assert [e['synthetic'] for e in report['claims'][0]['evidence']]==[False,True]
    assert report['assessments'][0]['current'] is False
    assert 'SYNTHETIC EXAMPLE' in render_markdown(report)


@pytest.mark.parametrize('stage',['start','report'])
@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
def test_other_workflow_writes_atomic_retries(store,stage,phase):
    if stage=='report':start(store);write(store,dict(type='finish',outcome='escalated',reason='Fixture boundary'))
    revision=store.load()[1]
    command=dict(type='report',report_id='R1') if stage=='report' else dict(type='start',workflow_id='W1',brief='Fixture',scope='Fixture',questions=['Why?'],max_alternatives=2)
    def fault(name):
        if name==phase:raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):write(store,command,oid='atomic',revision=revision,_fault=fault)
    reopened=PersistentEvidenceStore(store.ledger.path)
    assert reopened.load()[1]==revision+(phase=='after_commit')
    result=write(reopened,command,oid='atomic',revision=revision)
    assert result['state_revision']==revision+1


def test_idempotence_authorization_and_cross_kind_collisions(store):
    command=dict(type='start',workflow_id='W1',brief='Fixture',scope='Fixture',questions=['Why?'],max_alternatives=2)
    result=write(store,command,oid='start',revision=0)
    assert write(store,command,oid='start',revision=0)==result
    with pytest.raises(PermissionError):store.apply_workflow(command,operation_id='start',actor='fixture-human',rationale='Fixture workflow',expected_state_revision=0,authorize=lambda *args:False)
    changed=dict(command,brief='Different')
    with pytest.raises(ValueError):write(store,changed,oid='start',revision=0)
    with pytest.raises(ValueError):apply(store,[add_claim()],operation_id='start',expected_state_revision=1)
    with pytest.raises(ValueError):store.apply_gate(dict(type='propose',gate_id='G',action=dict(type='gated_action',action='publication',payload={})),operation_id='start',actor='fixture-human',rationale='Fixture',expected_state_revision=1,authorize=auth)


def test_record_is_single_write_and_phase_requires_record(store):
    ingest(store);start(store);advance(store,'discovery')
    gid=approve_transition(store,'definition')
    with pytest.raises(ValueError,match='record required'):write(store,dict(type='advance',to_phase='definition',gate_id=gid))
    record(store,'discovery',dict(evidence_ids=['s1'],notes='Fixture discovery'))
    with pytest.raises(ValueError,match='already recorded'):record(store,'discovery',dict(evidence_ids=['s1'],notes='Overwrite'))
    # The newly recorded content invalidates the earlier approval.
    with pytest.raises(PermissionError):write(store,dict(type='advance',to_phase='definition',gate_id=gid))


def test_report_mutation_tampering_fails_closed(store):
    import sqlite3
    complete(store)
    with sqlite3.connect(store.ledger.path) as db:
        db.execute("UPDATE state_mutations SET request='{}' WHERE kind='workflow' AND operation_id=(SELECT operation_id FROM state_mutations ORDER BY revision DESC LIMIT 1)")
    with pytest.raises(ValueError,match='integrity'):store.load()


def test_regenerated_report_keeps_stale_stage_warning(store):
    complete(store);revision=store.load()[1]
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=revision)
    write(store,dict(type='report',report_id='R2'))
    state,_=store.load();report=state.outputs['R2']
    assert report_is_current(state,'R2') and report['stage_currency']['synthesis'] is False
    assert 'STALE' in render_markdown(report)


def test_promoted_hypothesis_label_requires_and_preserves_approval(store):
    from test_gate_transactions import propose,decide,action as withdrawal
    from dd_research_runtime.gate_transactions import binding
    from test_gate_transactions import gate as gate_write
    ingest(store);apply(store,[add_claim()])
    action=withdrawal();action.update(disposition='promote_to_hypothesis',new_status='hypothesis')
    gate_write(store,dict(type='propose',gate_id='G1',action=action),'proposal',2)
    gate_write(store,dict(type='decide',gate_id='G1',decision='approve',proposal_digest=binding(action)),'decision',3)
    apply(store,[dict(action,gate_id='G1')],operation_id='promote',expected_state_revision=4)
    start(store);write(store,dict(type='finish',outcome='escalated',reason='Hypothesis remains untested'));write(store,dict(type='report',report_id='hypothesis'))
    assert store.load()[0].outputs['hypothesis']['claims'][0]['epistemic_label']=='hypothesis'


def test_brief_then_reviewed_synthetic_intake_to_report(store):
    from test_persistent_ingestion import batch,auth as ingest_auth
    start(store);advance(store,'discovery')
    validation,review=batch('synthetic-brief-first',synthetic=True)
    store.ingest(validation,review,operation_id='reviewed-intake',expected_state_revision=4,expected_ledger_revision=0,authorize=ingest_auth,source_snapshots={'synthetic-brief-first':{'text':'Exact passage synthetic-brief-first','location':'p1'}})
    claim=add_claim();claim['record']['evidence_ids']=['synthetic-brief-first']
    apply(store,[claim],expected_state_revision=5)
    record(store,'discovery',dict(evidence_ids=['synthetic-brief-first'],notes='Reviewed synthetic intake after the brief and discovery pause'))
    advance(store,'definition');record(store,'definition',dict(problem='Bounded fixture',claim_ids=['C1'],uncertainty_ids=[]))
    advance(store,'alternatives');data=alternatives()
    for item in data['alternatives']:item['evidence_ids']=['synthetic-brief-first']
    record(store,'alternatives',data);advance(store,'synthesis')
    record(store,'synthesis',dict(summary='Synthetic example remains inconclusive',claim_ids=['C1'],limitations='No real-world inference'))
    write(store,dict(type='finish',outcome='stopped',reason='Bound reached'))
    result=write(store,dict(type='report',report_id='brief-first'))
    reopened=PersistentEvidenceStore(store.ledger.path)
    assert reopened.load_workflow_operation('workflow-'+str(result['state_revision']-1))['request']['command']['report_id']=='brief-first'
    state,_=reopened.load();assert state.outputs['brief-first']['claims'][0]['evidence_origin']=='synthetic_only'
    assert reopened.load_source_snapshots('reviewed-intake')['synthetic-brief-first']['text']=='Exact passage synthetic-brief-first'


def test_stale_synthesis_cannot_stop_as_complete(store):
    ingest(store);apply(store,[add_claim()]);start(store)
    advance(store,'discovery');record(store,'discovery',dict(evidence_ids=['s1'],notes='Fixture'))
    advance(store,'definition');record(store,'definition',dict(problem='Fixture',claim_ids=['C1'],uncertainty_ids=[]))
    advance(store,'alternatives');record(store,'alternatives',alternatives());advance(store,'synthesis')
    record(store,'synthesis',dict(summary='Bounded',claim_ids=['C1'],limitations='Fixture'))
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=store.load()[1])
    with pytest.raises(ValueError,match='synthesis is stale'):write(store,dict(type='finish',outcome='stopped',reason='Cannot silently finish'))
    write(store,dict(type='finish',outcome='escalated',reason='Fresh review required'))
