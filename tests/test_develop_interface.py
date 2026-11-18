"""Separate alternative links through the local interface; synthetic fixtures only."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from dd_research_runtime.local_app import Workspace,ACTOR,_authorize
from test_local_app import request,source
from test_frame_revision import transition


def prepare(w):
    cid=w.create(dict(title='Synthetic separate alternatives',question='Which invented explanation needs investigation?',scope='Invented sources and simulated review only',max_visits=12,max_alternatives=4))
    for rid in ('first','second'):
        request(w,cid,'source',source(title='Invented '+rid,url='https://example.org/'+rid,passage='Invented '+rid+'.',snapshot='Context. Invented '+rid+'. Context.'),request_id=rid)
        request(w,cid,'claim',dict(claim='Invented interpretation '+rid,claim_type='descriptive',evidence_ids=['synthetic-'+rid],rationale='Fixture only'),request_id='interpretation-'+rid)
    request(w,cid,'phase_record',dict(record=dict(evidence_ids=['synthetic-first','synthetic-second'],notes='Two invented observations',perspectives=['Invented observer','Unstudied people'],limitations='Synthetic only'),rationale='Fixture'))
    transition(w,cid,'define')
    request(w,cid,'phase_record',dict(record=dict(problem='Compare invented explanations without combining their bases',claim_ids=['claim-interpretation-first','claim-interpretation-second'],uncertainty_ids=[],success_criteria=['Preserve uncertainty explicitly']),rationale='Fixture'))
    transition(w,cid,'develop');return cid


def record():
    return dict(alternatives=[dict(alternative_id='option-'+str(i),hypothesis='Invented explanation '+str(i),test='Proposed investigation '+str(i)+'; not executed',claim_ids=['claim-interpretation-'+rid],evidence_ids=['synthetic-'+rid],limitations='Invented '+rid+' only') for i,rid in [(1,'first'),(2,'second')]])

@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');return w,prepare(w)


def test_distinct_links_survive_restart_original_visit_report_and_checkpoint(case):
    w,cid=case;before=w.view(cid);value=record()
    request(w,cid,'phase_record',dict(record=value,rationale='Retain separate alternatives'))
    saved=Workspace(w.path).view(cid)
    assert saved['state']['workflow']['records']['develop']==value and saved['state']['evidence']==before['state']['evidence']
    assert saved['state']['human_gates']==before['state']['human_gates'] and saved['ledger_revision']==before['ledger_revision']
    original=w.visit(cid,'V3');assert original['visit']['record']==value
    transition(w,cid,'deliver')
    delivery=dict(selected_alternative_id='option-1',evaluations=[dict(evaluation_id='evaluation-1',alternative_id='option-1',method='Inspect invented material; no real experiment',evidence_ids=['synthetic-first'],outcome='inconclusive',limitations='Synthetic only')],decision='stop_unresolved',summary='No real-world result',claim_ids=['claim-interpretation-first'],limitations='Synthetic only',criterion_assessments=[dict(criterion_index=0,outcome='unknown',evaluation_ids=['evaluation-1'],rationale='No real evidence',next_research='Gather independently reviewed evidence')])
    request(w,cid,'phase_record',dict(record=delivery,rationale='Fixture'))
    request(w,cid,'finish',dict(outcome='stopped',rationale='Stop unresolved fixture'));request(w,cid,'report',dict(rationale='Fixture report'))
    view=w.view(cid);report=view['state']['outputs'][view['reports'][0]['report_id']]
    assert report['workflow']['records']['develop']==value
    assert all(e['evidence']['synthetic'] for c in report['claims'] for e in c['evidence'])
    data,_=w.backup(cid,view['revision']);preview=w.inspect_backup(data);restored=w.restore_backup(data,preview['checkpoint_digest'])
    assert w.view(restored['case_id'])['state']==view['state'] and not restored['approval_granted']
    assert w.visit(restored['case_id'],'V3')['visit']['record']==value

@pytest.mark.parametrize('change',['missing_claim','unknown_claim','duplicate_claim','unknown_evidence','duplicate_evidence','missing_hypothesis','missing_test','missing_limits','duplicate_id','too_few','too_many','extra_field'])
def test_invalid_separate_alternative_submission_has_no_partial_save(case,change):
    w,cid=case;before=w.view(cid);value=record();item=value['alternatives'][1]
    if change=='missing_claim':item['claim_ids']=[]
    elif change=='unknown_claim':item['claim_ids']=['missing']
    elif change=='duplicate_claim':item['claim_ids']=['claim-interpretation-second','claim-interpretation-second']
    elif change=='unknown_evidence':item['evidence_ids']=['missing']
    elif change=='duplicate_evidence':item['evidence_ids']=['synthetic-second','synthetic-second']
    elif change=='missing_hypothesis':item['hypothesis']=''
    elif change=='missing_test':item['test']=''
    elif change=='missing_limits':item['limitations']=''
    elif change=='duplicate_id':item['alternative_id']='option-1'
    elif change=='too_few':value['alternatives'].pop()
    elif change=='too_many':value['alternatives']=[dict(value['alternatives'][0],alternative_id='option-'+str(i)) for i in range(5)]
    else:item['evaluation_outcome']='supported'
    with pytest.raises(ValueError):request(w,cid,'phase_record',dict(record=value,rationale='Invalid fixture'))
    assert w.view(cid)==before


def test_empty_evidence_list_is_retained_without_copying_another_alternative(case):
    w,cid=case;value=record();value['alternatives'][1]['evidence_ids']=[]
    request(w,cid,'phase_record',dict(record=value,rationale='Unbacked alternative stays explicit'))
    saved=w.view(cid)['state']['workflow']['records']['develop']['alternatives']
    assert saved[0]['evidence_ids']==['synthetic-first'] and saved[1]['evidence_ids']==[]
    assert saved[0]['claim_ids']==['claim-interpretation-first'] and saved[1]['claim_ids']==['claim-interpretation-second']


def test_case_alternative_budget_accepts_exact_limit(case):
    w,cid=case;value=record();value['alternatives'] += [dict(value['alternatives'][0],alternative_id='option-'+str(i)) for i in (3,4)]
    request(w,cid,'phase_record',dict(record=value,rationale='Exact case budget fixture'))
    assert w.view(cid)['state']['workflow']['records']['develop']==value


def test_concurrent_stale_tabs_cannot_combine_alternatives_from_two_submissions(case):
    w,cid=case;before=w.view(cid)
    def save(i):
        value=record();value['alternatives'][0]['hypothesis']='Submission '+str(i)
        try:return request(w,cid,'phase_record',dict(record=value,rationale='Concurrent fixture'),request_id='parallel-'+str(i),expected_revision=before['revision'],expected_ledger_revision=before['ledger_revision'])
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,range(2)))
    assert sum(r is not None for r in results)==1
    after=w.view(cid);assert after['revision']==before['revision']+1
    rows=after['state']['workflow']['records']['develop']['alternatives']
    assert rows[0]['evidence_ids']==['synthetic-first'] and rows[1]['evidence_ids']==['synthetic-second']


def test_later_claim_edit_preserves_original_alternative_links_and_report_context(case):
    w,cid=case;value=record();request(w,cid,'phase_record',dict(record=value,rationale='Fixture'))
    before=w.visit(cid,'V3');view=w.view(cid)
    w.store(cid).apply_analysis([dict(type='update_claim',claim_id='claim-interpretation-second',patch=dict(claim='Later synthetic interpretation'))],operation_id='later-edit',actor=ACTOR,rationale='Fixture',expected_state_revision=view['revision'],authorize=_authorize)
    after=w.view(cid);assert after['currency']['develop'] is False
    original=w.visit(cid,'V3');assert original['visit']==before['visit'] and original['context']==before['context']
    assert original['visit']['record']['alternatives'][1]['claim_ids']==['claim-interpretation-second']
    assert original['context']['claims']['claim-interpretation-second']['claim']=='Invented interpretation second'
