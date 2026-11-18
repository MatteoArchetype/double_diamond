"""Advisory navigation and explicit synthetic onboarding, never real research."""
import copy
import io
import json
import threading
import pytest
from test_persistent_ingestion import store
from test_double_diamond import begin,record,move,record_for,approve,finish
from test_workflow import write
from test_analysis_transactions import apply
from dd_research_runtime.interface_guidance import build_guidance
from dd_research_runtime.double_diamond import transition_action
from dd_research_runtime.local_app import Workspace,Handler
from dd_research_runtime.gate_transactions import binding


def guidance(store):return build_guidance(store.load()[0])


def test_empty_case_points_to_explicit_source_review_without_writing(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=w.create(dict(title='Synthetic empty test',question='What remains unknown?',scope='Test only',max_visits=8,max_alternatives=3))
    before=w.store(cid).load();view=w.view(cid);g=view['guidance']
    assert g['step']=='review_source' and g['navigation']['tab']=='Sources'
    assert g['advisory_only'] and not g['execution_authorized'] and g['evidence_counts']==dict(synthetic=0,source_records=0)
    assert w.store(cid).load()[0].snapshot()==before[0].snapshot() and view['revision']==before[1]


@pytest.mark.parametrize('phase',['discover','define','develop','deliver'])
def test_open_phases_point_to_their_actual_work_without_progressing(store,phase):
    begin(store)
    for current in ['discover','define','develop']:
        if current==phase:break
        record(store,current);move(store,{'discover':'define','define':'develop','develop':'deliver'}[current])
    before=store.load()[0].snapshot();result=guidance(store)
    assert result['step']=='record_'+phase and result['navigation']['tab']=='Research'
    assert result['phase']==phase and result['phases'][['discover','define','develop','deliver'].index(phase)]['status']=='not_recorded'
    assert store.load()[0].snapshot()==before


@pytest.mark.parametrize('phase',['discover','define','develop'])
def test_saved_phase_proposes_navigation_not_approval_or_execution(store,phase):
    begin(store)
    for current in ['discover','define','develop']:
        record(store,current)
        if current==phase:break
        move(store,{'discover':'define','define':'develop'}[current])
    result=guidance(store)
    assert result['step']=='review_transition' and result['phase']==phase
    assert result['execution_authorized'] is False and result['research_reviews_pending']==0
    assert set(result['navigation'])=={'tab','label'}


def pending(store):
    begin(store);record(store,'discover');state,revision=store.load();action=transition_action(state,'define','Synthetic progression')
    store.apply_gate(dict(type='propose',gate_id='guided-review',action=action),operation_id='guided-proposal',actor='fixture-human',rationale='Simulated proposal',expected_state_revision=revision,authorize=lambda actor,cap:True)
    return action


def test_pending_and_approved_changes_remain_separate_steps(store):
    action=pending(store);before=store.load()[0].snapshot();result=guidance(store)
    assert result['step']=='review_pending' and result['navigation']['tab']=='Approvals' and result['research_reviews_pending']==1
    assert store.load()[0].snapshot()==before and result['phase']=='discover'
    revision=store.load()[1]
    store.apply_gate(dict(type='decide',gate_id='guided-review',decision='approve',proposal_digest=binding(action)),operation_id='guided-decision',actor='fixture-human',rationale='Simulated review',expected_state_revision=revision,authorize=lambda actor,cap:True)
    before=store.load()[0].snapshot();result=guidance(store)
    assert result['step']=='apply_separately' and result['approved_changes_unapplied']==1 and result['phase']=='discover'
    assert store.load()[0].snapshot()==before


def test_publication_gate_is_never_treated_as_a_research_navigation_permission(store):
    begin(store);result=guidance(store)
    assert result['research_reviews_pending']==result['approved_changes_unapplied']==0
    assert result['execution_authorized'] is False
    assert store.load()[0].human_gates['publication']['status']!='approved'


def ready_delivery(store,decision='stop_unresolved'):
    begin(store)
    for current,target in [('discover','define'),('define','develop'),('develop','deliver')]:record(store,current);move(store,target)
    value=record_for('deliver');value['decision']=decision;record(store,'deliver',value)


def test_changed_interpretation_does_not_get_false_ready_guidance(store):
    ready_delivery(store);revision=store.load()[1]
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(claim='Changed synthetic interpretation'))],operation_id='change',expected_state_revision=revision)
    result=guidance(store)
    assert result['step']=='review_changed_basis' and any(p['status']=='needs_review' for p in result['phases'])
    assert not result['execution_authorized']


def test_deliver_revision_does_not_suggest_a_finished_result(store):
    ready_delivery(store,'revise');result=guidance(store)
    assert result['step']=='return_for_revision' and result['navigation']['tab']=='Research'
    assert result['status']=='active'


def test_stopping_and_saved_draft_have_distinct_guidance(store):
    ready_delivery(store);assert guidance(store)['step']=='finish_or_return'
    write(store,dict(type='finish',outcome='stopped',reason='Synthetic unresolved pass'))
    assert guidance(store)['step']=='prepare_report'
    write(store,dict(type='report',report_id='R1'));result=guidance(store)
    assert result['step']=='inspect_report' and result['current_report_count']==1
    assert not store.load()[0].outputs['R1']['publication_authorized']


def test_escalation_does_not_invent_complete_findings(store):
    begin(store);write(store,dict(type='finish',outcome='escalated',reason='Insufficient synthetic evidence'))
    result=guidance(store)
    assert result['step']=='prepare_report' and result['status']=='escalated'
    assert all(p['status']=='not_recorded' for p in result['phases'])


def test_visit_budget_does_not_block_recording_the_last_visit_or_expand_limit(store):
    begin(store,budget=4);record(store,'discover')
    for i in range(3):
        move(store,'discover','revisit',gid='return-'+str(i))
        if i<2:record(store,'discover')
    result=guidance(store)
    assert result['visits_remaining']==0 and result['step']=='record_discover'
    assert 'finish the current visit' in result['budget_note']
    record(store,'discover');result=guidance(store)
    assert result['step']=='budget_exhausted' and store.load()[0].workflow['max_visits']==4


def test_last_deliver_visit_can_still_finish(store):
    begin(store,budget=4)
    for current,target in [('discover','define'),('define','develop'),('develop','deliver')]:record(store,current);move(store,target)
    record(store,'deliver');result=guidance(store)
    assert result['visits_remaining']==0 and result['step']=='finish_or_return'
    write(store,dict(type='finish',outcome='stopped',reason='Bounded synthetic pass'))
    assert guidance(store)['step']=='prepare_report'


def test_unsupported_workflow_refused_without_inference(store):
    with pytest.raises(ValueError,match='Double Diamond'):guidance(store)


def test_guidance_result_is_detached_and_contains_no_mutation_command(store):
    begin(store);result=guidance(store);result['phases'][0]['status']='saved';result['navigation']['tab']='Publish'
    again=guidance(store)
    assert again['phases'][0]['status']=='not_recorded' and again['navigation']['tab']=='Research'
    assert 'command' not in again and 'approve' not in again['navigation']


def post(w,body,*,headers=None,path='/api/example'):
    class Server:origin='http://127.0.0.1:12345';token='private';workspace=w;mutation_lock=threading.Lock()
    handler=object.__new__(Handler);handler.server=Server();handler.path=path
    data=json.dumps(body).encode();handler.rfile=io.BytesIO(data)
    handler.headers=dict(Host='127.0.0.1:12345',Origin=Server.origin,Authorization='Bearer private',**{'Content-Type':'application/json','Content-Length':str(len(data))})
    if headers is not None:
        for key,value in headers.items():
            if value is None:handler.headers.pop(key,None)
            else:handler.headers[key]=value
    replies=[];handler._reply=lambda *args:replies.append(args);handler.do_POST();return replies[0]


@pytest.mark.parametrize('body',[{},None,{'kind':'real_research'},{'kind':True},{'kind':'synthetic_learning_example','synthetic':False}])
def test_example_route_refuses_ambiguous_or_real_research_requests(tmp_path,body):
    w=Workspace(tmp_path/'workspace');result=post(w,body)
    assert result[0]==400 and w.cases()==[]


@pytest.mark.parametrize('headers',[{'Authorization':None},{'Authorization':'Bearer wrong'},{'Origin':None},{'Origin':'https://elsewhere.invalid'},{'Host':'elsewhere.invalid'}])
def test_example_creation_requires_private_local_session(tmp_path,headers):
    w=Workspace(tmp_path/'workspace');result=post(w,dict(kind='synthetic_learning_example'),headers=headers)
    assert result[0]==403 and w.cases()==[]


def test_example_route_creates_explicitly_synthetic_case_and_preserves_real_workspace(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=w.create(dict(title='Empty user case',question='What remains unknown?',scope='No research yet',max_visits=8,max_alternatives=3));before=w.view(cid)
    result=post(w,dict(kind='synthetic_learning_example'))
    assert result[0]==201 and result[1]['synthetic_example'] is True
    example=w.view(result[1]['case_id'])
    assert example['meta']['synthetic_example'] and example['guidance']['synthetic_example']
    assert example['guidance']['step']=='inspect_report'
    assert example['reports'][0]['current'] is True and example['reports'][0]['report_id']=='after-iteration'
    assert example['reports'][-1]['current'] is False
    assert example['guidance']['evidence_counts']['synthetic']>0 and example['guidance']['evidence_counts']['source_records']==0
    assert all(e['synthetic'] for e in example['state']['evidence'].values())
    assert all(not r['publication_authorized'] for r in example['state']['outputs'].values())
    assert not getattr(w.store(result[1]['case_id']).load()[0],'acceptance_records',{})
    assert w.view(cid)==before and len(w.cases())==2


def test_each_explicit_example_request_creates_a_separate_case_without_retrying(tmp_path):
    w=Workspace(tmp_path/'workspace')
    first=post(w,dict(kind='synthetic_learning_example'));second=post(w,dict(kind='synthetic_learning_example'))
    assert first[0]==second[0]==201 and first[1]['case_id']!=second[1]['case_id'] and len(w.cases())==2
    assert all(c['synthetic_example'] for c in w.cases())


def test_current_reports_are_newest_first_and_historical_drafts_are_retained(tmp_path):
    from test_local_app import request
    w=Workspace(tmp_path/'workspace');cid=w.demo();before=w.view(cid)
    request(w,cid,'report',dict(rationale='Another explicitly requested synthetic draft'),request_id='000-new-draft')
    result=w.view(cid)
    assert result['reports'][0]['report_id']=='report-000-new-draft' and result['reports'][0]['current']
    assert result['reports'][1]['report_id']=='after-iteration' and result['reports'][1]['current']
    assert result['reports'][-1]['report_id']=='before-iteration' and not result['reports'][-1]['current']
    assert all(result['state']['outputs'][key]==value for key,value in before['state']['outputs'].items())
    assert result['guidance']['current_report_count']==2
