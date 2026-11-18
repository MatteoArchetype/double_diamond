"""Multiple-evaluation local interface transactions; invented fixtures only."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from dd_research_runtime.local_app import Workspace
from test_local_app import create,request,source
from test_frame_revision import transition


def prepare(w):
    cid=create(w)
    for rid in ('first','second'):
        request(w,cid,'source',source(title='Invented '+rid,passage='Invented '+rid+'.',snapshot='Context. Invented '+rid+'. Context.'),request_id=rid)
    request(w,cid,'claim',dict(claim='Synthetic tentative interpretation',claim_type='descriptive',evidence_ids=['synthetic-first'],rationale='Invented fixture only'),request_id='interpretation')
    claim='claim-interpretation'
    records={
        'discover':dict(evidence_ids=['synthetic-first','synthetic-second'],notes='Invented observations',perspectives=['Fixture observer','Unstudied people'],limitations='Synthetic only'),
        'define':dict(problem='Bound a synthetic explanation',claim_ids=[claim],uncertainty_ids=[],success_criteria=['Bound the description','Address contrary evidence']),
        'develop':dict(alternatives=[dict(alternative_id='option-'+str(i),hypothesis='Invented explanation '+str(i),test='Proposed test only',claim_ids=[claim],evidence_ids=['synthetic-first'],limitations='Synthetic only') for i in (1,2)])}
    for phase,target in [('discover','define'),('define','develop'),('develop','deliver')]:
        request(w,cid,'phase_record',dict(record=records[phase],rationale='Fixture only'));transition(w,cid,target)
    return cid


def record():
    return dict(selected_alternative_id='option-1',evaluations=[
        dict(evaluation_id='evaluation-1',alternative_id='option-1',method='Compare first invented passage',evidence_ids=['synthetic-first'],outcome='supported',limitations='Not real research'),
        dict(evaluation_id='evaluation-2',alternative_id='option-1',method='Compare contrary invented passage',evidence_ids=['synthetic-second'],outcome='unsupported',limitations='Not real research'),
        dict(evaluation_id='evaluation-3',alternative_id='option-2',method='Inspect alternative with no new evidence',evidence_ids=[],outcome='inconclusive',limitations='No completed experiment')],
        decision='stop_unresolved',summary='Synthetic mixed results; no real-world answer.',claim_ids=['claim-interpretation'],limitations='Invented evidence only',criterion_assessments=[
        dict(criterion_index=0,outcome='met',evaluation_ids=['evaluation-1'],rationale='First invented passage addresses criterion',next_research=''),
        dict(criterion_index=1,outcome='not_met',evaluation_ids=['evaluation-2'],rationale='Contrary invented passage challenges criterion',next_research='Acquire independently reviewed evidence')])

@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');return w,prepare(w)


def test_multiple_evaluations_persist_through_report_visit_and_browser_checkpoint(case):
    w,cid=case;before=w.view(cid);value=record()
    request(w,cid,'phase_record',dict(record=value,rationale='Record separate synthetic evaluations'))
    after=Workspace(w.path).view(cid)
    assert after['state']['workflow']['records']['deliver']==value
    assert after['state']['human_gates']==before['state']['human_gates']
    assert after['state']['evidence']==before['state']['evidence']
    assert w.visit(cid,'V4')['visit']['record']==value
    request(w,cid,'finish',dict(outcome='stopped',rationale='Stop with mixed synthetic outcomes'))
    request(w,cid,'report',dict(rationale='Synthetic report'))
    view=w.view(cid);report=view['state']['outputs'][view['reports'][0]['report_id']]
    trace=report['decision_trace']['criteria']
    assert trace[0]['evidence_ids']==['synthetic-first'] and trace[1]['evidence_ids']==['synthetic-second']
    data,_=w.backup(cid,view['revision']);preview=w.inspect_backup(data);restored=w.restore_backup(data,preview['checkpoint_digest'])
    assert w.view(restored['case_id'])['state']==view['state']
    assert preview['evidence_counts']==dict(synthetic=2,source_records=0) and not restored['approval_granted']

@pytest.mark.parametrize('change',['unknown_link','wrong_alternative','missing_selected_evaluation','duplicate_id','missing_method','missing_limits','missing_evidence','unsupported_met','supported_not_met','missing_next_research','recommend_with_gap','too_many','none'])
def test_invalid_multi_evaluation_submission_has_no_partial_record_or_audit(case,change):
    w,cid=case;before=w.view(cid);value=record()
    if change=='unknown_link':value['criterion_assessments'][0]['evaluation_ids']=['removed-evaluation']
    elif change=='wrong_alternative':value['criterion_assessments'][0]['evaluation_ids']=['evaluation-3']
    elif change=='missing_selected_evaluation':
        for item in value['evaluations']:item['alternative_id']='option-2'
    elif change=='duplicate_id':value['evaluations'][1]['evaluation_id']='evaluation-1'
    elif change=='missing_method':value['evaluations'][1]['method']=''
    elif change=='missing_limits':value['evaluations'][1]['limitations']=''
    elif change=='missing_evidence':value['evaluations'][1]['evidence_ids']=[]
    elif change=='unsupported_met':value['criterion_assessments'][0]['evaluation_ids']=['evaluation-2']
    elif change=='supported_not_met':value['criterion_assessments'][1]['evaluation_ids']=['evaluation-1']
    elif change=='missing_next_research':value['criterion_assessments'][1]['next_research']=''
    elif change=='recommend_with_gap':value['decision']='recommend'
    elif change=='too_many':value['evaluations']=[dict(value['evaluations'][0],evaluation_id='E'+str(i)) for i in range(21)]
    else:value['evaluations']=[]
    with pytest.raises(ValueError):request(w,cid,'phase_record',dict(record=value,rationale='Invalid fixture'))
    assert w.view(cid)==before


def test_maximum_twenty_evaluations_are_retained_without_collapsing(case):
    w,cid=case;value=record()
    value['evaluations'] += [dict(value['evaluations'][2],evaluation_id='evaluation-'+str(i)) for i in range(4,21)]
    request(w,cid,'phase_record',dict(record=value,rationale='Bounded twenty-row fixture'))
    assert w.view(cid)['state']['workflow']['records']['deliver']==value


def test_two_tabs_cannot_overwrite_a_saved_deliver_record(case):
    w,cid=case;before=w.view(cid)
    def save(i):
        try:return request(w,cid,'phase_record',dict(record=record(),rationale='Concurrent fixture '+str(i)),expected_revision=before['revision'],expected_ledger_revision=before['ledger_revision'])
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,range(2)))
    assert sum(r is not None for r in results)==1
    after=w.view(cid);assert after['revision']==before['revision']+1 and after['state']['workflow']['records']['deliver']==record()


def test_multiple_selected_evaluations_can_inform_one_unknown_criterion(case):
    w,cid=case;value=record();value['criterion_assessments'][1].update(outcome='unknown',evaluation_ids=['evaluation-1','evaluation-2'])
    request(w,cid,'phase_record',dict(record=value,rationale='Retain disagreement explicitly'))
    assert w.view(cid)['state']['workflow']['records']['deliver']['criterion_assessments'][1]['evaluation_ids']==['evaluation-1','evaluation-2']
