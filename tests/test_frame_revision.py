"""Synthetic revision walkthroughs. No actual research or human acceptance."""
import copy
import json
import uuid
from pathlib import Path
import pytest
from dd_research_runtime.local_app import Workspace,Handler,ACTOR,_authorize
from dd_research_runtime.frame_revision import read_frame_draft
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.runtime import ResearchState
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint
from test_local_app import request,source


def transition(w,cid,target):
    rid=uuid.uuid4().hex
    request(w,cid,'propose_transition',dict(target=target,rationale='Synthetic walkthrough progression'),request_id=rid)
    request(w,cid,'decide_gate',dict(gate_id='gate-'+rid,decision='approve',rationale='Simulated fixture approval'))
    request(w,cid,'apply_gate',dict(gate_id='gate-'+rid,rationale='Explicit simulated fixture application'))


def prepare_workspace(w):
    cid=w.create(dict(title='Synthetic revision walkthrough',question='How should this invented explanation be bounded?',scope='Invented evidence and simulated approvals only. No real research or acceptance.',max_visits=12,max_alternatives=3))
    (w.case_path(cid)/'case-info.json').write_text(json.dumps(dict(title='Synthetic revision walkthrough',synthetic_example=True)))
    request(w,cid,'source',source(),request_id='synthetic-source')
    request(w,cid,'claim',dict(claim='SYNTHETIC: this interpretation remains tentative.',claim_type='descriptive',evidence_ids=['synthetic-synthetic-source'],rationale='Synthetic advisory interpretation'),request_id='interpretation')
    store=w.store(cid)
    store.apply_analysis([dict(type='put_uncertainty',record=dict(uncertainty_id=uid,question=question,status='open')) for uid,question in [('linked-gap','Does the invented explanation transfer?'),('other-gap','What other perspectives are missing?')]],operation_id='fixture-gaps',actor=ACTOR,rationale='Synthetic gaps only',expected_state_revision=w.view(cid)['revision'],authorize=_authorize)
    eid='synthetic-synthetic-source';claim='claim-interpretation'
    records={
        'discover':dict(evidence_ids=[eid],notes='An invented observation is available.',perspectives=['Synthetic observer','Real users: not studied'],limitations='Invented material only.'),
        'define':dict(problem='Explain the invented observation within its context.',claim_ids=[claim],uncertainty_ids=['linked-gap'],success_criteria=['Retain explicit uncertainty']),
        'develop':dict(alternatives=[dict(alternative_id='A'+str(i),hypothesis='Synthetic explanation '+str(i),test='Compare the invented passage; no experiment performed',claim_ids=[claim],evidence_ids=[eid],limitations='Invented evidence only') for i in range(2)]),
        'deliver':dict(selected_alternative_id='A0',evaluations=[dict(evaluation_id='E1',alternative_id='A0',method='Synthetic passage comparison; not an experiment',evidence_ids=[eid],outcome='inconclusive',limitations='No real evidence')],decision='stop_unresolved',summary='No real-world finding. The invented example remains unresolved.',claim_ids=[claim],limitations='Synthetic only',criterion_assessments=[dict(criterion_index=0,outcome='unknown',evaluation_ids=['E1'],rationale='No real evidence has been gathered',next_research='Acquire independently reviewed evidence')])}
    for i,phase in enumerate(['discover','define','develop','deliver']):
        request(w,cid,'phase_record',dict(record=records[phase],rationale='Synthetic fixture finding'))
        if i<3:transition(w,cid,['define','develop','deliver'][i])
    request(w,cid,'finish',dict(outcome='stopped',rationale='Stop the synthetic pass with uncertainty'))
    request(w,cid,'report',dict(rationale='Retain the original synthetic draft'))
    return cid


@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=prepare_workspace(w);return w,cid


def test_copy_requires_reviewed_return_and_has_no_saved_side_effects(case):
    w,cid=case
    with pytest.raises(ValueError,match='open Define'):w.frame_draft(cid,'V2',w.view(cid)['revision'])
    transition(w,cid,'define');before=w.view(cid);path=w.case_path(cid)/'research.sqlite';raw=path.read_bytes()
    draft=w.frame_draft(cid,'V2',before['revision'])
    assert draft['type']=='unsaved_frame_draft' and draft['target_visit_id']=='V5'
    assert not draft['approval_granted'] and not draft['persisted']
    assert draft['record']==before['state']['workflow']['visits'][1]['record']
    assert draft['record']['uncertainty_ids']==['linked-gap'] and 'other-gap' not in draft['record']['uncertainty_ids']
    assert w.view(cid)==before and path.read_bytes()==raw


def test_draft_copy_is_detached(case):
    w,cid=case;transition(w,cid,'define');revision=w.view(cid)['revision'];draft=w.frame_draft(cid,'V2',revision)
    draft['record']['problem']='Detached edit';draft['record']['uncertainty_ids'].clear()
    again=w.frame_draft(cid,'V2',revision)
    assert again['record']['problem']!='Detached edit' and again['record']['uncertainty_ids']==['linked-gap']


def test_revised_frame_requires_separate_review_survives_restart_and_preserves_history(case):
    w,cid=case;before=w.view(cid);transition(w,cid,'define');draft=w.frame_draft(cid,'V2',w.view(cid)['revision'])
    revised=copy.deepcopy(draft['record']);revised['problem']='Identify what remains unknown about the invented observation.'
    result=request(w,cid,'phase_record',dict(record=revised,rationale='Narrow this synthetic frame'),request_id='new-frame')
    assert 'proposed' in result['notice']
    w=Workspace(w.path);pending=w.view(cid)
    assert 'define' not in pending['state']['workflow']['records']
    assert pending['state']['human_gates']['gate-new-frame']['status']=='pending_review'
    with pytest.raises(PermissionError):request(w,cid,'apply_gate',dict(gate_id='gate-new-frame',rationale='Not approved'))
    request(w,cid,'decide_gate',dict(gate_id='gate-new-frame',decision='approve',rationale='Simulated exact frame review'))
    assert 'define' not in Workspace(w.path).view(cid)['state']['workflow']['records']
    request(w,cid,'apply_gate',dict(gate_id='gate-new-frame',rationale='Explicit simulated application'))
    final=Workspace(w.path).view(cid)
    assert final['state']['workflow']['records']['define']==revised
    assert final['state']['workflow']['visits'][:4]==before['state']['workflow']['visits']
    assert final['state']['evidence']==before['state']['evidence'] and final['ledger_revision']==before['ledger_revision']
    assert final['state']['outputs']==before['state']['outputs'] and not any(r['current'] for r in final['reports'])
    assert w.visit(cid,'V2')['visit']['record']['problem']!=revised['problem']


def test_identical_frame_save_copies_no_old_approval(case):
    w,cid=case;transition(w,cid,'define');before=w.view(cid);draft=w.frame_draft(cid,'V2',before['revision'])
    request(w,cid,'phase_record',dict(record=draft['record'],rationale='Reconsidered the same synthetic frame'))
    final=w.view(cid)
    assert len(final['state']['human_gates'])==len(before['state']['human_gates'])
    assert final['state']['workflow']['visits'][-1]['record']==draft['record']
    with pytest.raises(ValueError,match='open Define'):w.frame_draft(cid,'V2',final['revision'])


def test_stale_draft_and_stale_save_fail_without_mutation(case):
    w,cid=case;transition(w,cid,'define');revision=w.view(cid)['revision'];draft=w.frame_draft(cid,'V2',revision)
    request(w,cid,'propose_transition',dict(target='discover',rationale='Synthetic intervening proposal'))
    before=w.view(cid)
    with pytest.raises(RuntimeError,match='changed'):w.frame_draft(cid,'V2',revision)
    with pytest.raises(RuntimeError,match='changed'):request(w,cid,'phase_record',dict(record=draft['record'],rationale='Stale draft'),expected_revision=revision)
    assert w.view(cid)==before


@pytest.mark.parametrize('visit',['V1','V3','V4','V5','unknown','../V2'])
def test_only_saved_original_define_frames_can_be_copied(case,visit):
    w,cid=case;transition(w,cid,'define');before=w.view(cid)
    with pytest.raises(ValueError):w.frame_draft(cid,visit,before['revision'])
    assert w.view(cid)==before


@pytest.mark.parametrize('revision',[None,True,-1,'1',1.1])
def test_current_revision_is_required(case,revision):
    w,cid=case;transition(w,cid,'define')
    with pytest.raises(ValueError,match='revision'):w.frame_draft(cid,'V2',revision)


def test_prejournal_original_context_is_not_copied(case,tmp_path):
    w,cid=case;transition(w,cid,'define');bootstrap=PersistentEvidenceStore(tmp_path/'bootstrap.sqlite');bootstrap.initialize(w.store(cid).load()[0])
    with pytest.raises(ValueError,match='unavailable'):read_frame_draft(bootstrap.ledger.path,'V2',expected_revision=0)


def test_rejected_frame_does_not_replace_previous_findings(case):
    w,cid=case;transition(w,cid,'define');draft=w.frame_draft(cid,'V2',w.view(cid)['revision']);value=draft['record'];value['success_criteria']=['A revised criterion']
    request(w,cid,'phase_record',dict(record=value,rationale='Synthetic criterion proposal'),request_id='reject-frame')
    request(w,cid,'decide_gate',dict(gate_id='gate-reject-frame',decision='reject',rationale='Simulated rejection'))
    with pytest.raises(PermissionError):request(w,cid,'apply_gate',dict(gate_id='gate-reject-frame',rationale='Rejected'))
    assert w.view(cid)['state']['workflow']['visits'][1]['record']['success_criteria']==['Retain explicit uncertainty']
    assert w.view(cid)['state']['workflow']['visits'][-1]['record'] is None


def test_checkpoint_restores_pending_revision_and_proposal(case,tmp_path):
    w,cid=case;transition(w,cid,'define');draft=w.frame_draft(cid,'V2',w.view(cid)['revision']);record=draft['record'];record['problem']='Synthetic revised question'
    request(w,cid,'phase_record',dict(record=record,rationale='Synthetic revision'),request_id='checkpoint-frame')
    checkpoint=tmp_path/'pending.zip';create_checkpoint(w.store(cid),checkpoint);target=tmp_path/'restored.sqlite';restore_checkpoint(checkpoint,target)
    revision=PersistentEvidenceStore(target).load()[1];restored=read_frame_draft(target,'V2',expected_revision=revision)
    assert restored['record']==w.visit(cid,'V2')['visit']['record'] and not restored['approval_granted']
    assert PersistentEvidenceStore(target).load()[0].human_gates['gate-checkpoint-frame']['status']=='pending_review'


def http_get(w,path,authenticated=True):
    handler=object.__new__(Handler)
    class Server:origin='http://127.0.0.1:12345';token='private';workspace=w
    handler.server=Server();handler.headers=dict(Host='127.0.0.1:12345')
    if authenticated:handler.headers['Authorization']='Bearer private'
    handler.path=path;replies=[];handler._reply=lambda *args:replies.append(args);handler.do_GET();return replies[0]


def test_http_draft_requires_authentication_and_exact_revision(case):
    w,cid=case;transition(w,cid,'define');revision=w.view(cid)['revision'];path='/api/frame-draft?case='+cid+'&visit=V2&revision='+str(revision)
    assert http_get(w,path,False)[0]==403
    result=http_get(w,path);assert result[0]==200 and result[1]['persisted'] is False
    assert http_get(w,path.replace('revision='+str(revision),'revision=0'))[0]==409
    assert http_get(w,path.split('&revision=')[0])[0]==400
    assert http_get(w,path.replace('revision='+str(revision),'revision=true'))[0]==400


def test_full_research_loop_after_revision_reopens_and_exports_current_report(case):
    w,cid=case;original=w.view(cid);transition(w,cid,'define');record=w.frame_draft(cid,'V2',w.view(cid)['revision'])['record']
    record['problem']='Bound the invented explanation to its observed context.'
    request(w,cid,'phase_record',dict(record=record,rationale='Synthetic revised frame'),request_id='loop-frame')
    request(w,cid,'decide_gate',dict(gate_id='gate-loop-frame',decision='approve',rationale='Simulated review'))
    request(w,cid,'apply_gate',dict(gate_id='gate-loop-frame',rationale='Simulated explicit application'))
    for phase in ('develop','deliver'):
        transition(w,cid,phase)
        prior=next(v['record'] for v in original['state']['workflow']['visits'] if v['phase']==phase)
        request(w,cid,'phase_record',dict(record=prior,rationale='Explicit synthetic reassessment for this new visit'))
    request(w,cid,'finish',dict(outcome='stopped',rationale='Stop with the synthetic conclusion unresolved'))
    request(w,cid,'report',dict(rationale='New synthetic report after reassessment'))
    final=Workspace(w.path).view(cid)
    assert final['state']['workflow']['status']=='stopped' and len(final['state']['workflow']['visits'])==7
    assert final['state']['workflow']['visits'][:4]==original['state']['workflow']['visits']
    assert sum(r['current'] for r in final['reports'])==1 and len(final['reports'])==2
    assert final['state']['evidence']==original['state']['evidence'] and final['ledger_revision']==1
    assert all(e['synthetic'] for e in final['state']['evidence'].values())
    from dd_research_runtime.reporting import render_markdown
    latest=next(r['report_id'] for r in final['reports'] if r['current'])
    markdown=render_markdown(final['state']['outputs'][latest])
    assert final['state']['outputs'][latest]['workflow']['records']['define']==record
    assert 'Bound the invented explanation to its observed context\\.' in markdown and 'Synthetic' in markdown


def test_genuine_old_checkpoint_can_prepare_draft_without_migration(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=uuid.uuid4().hex;folder=w.path/cid;folder.mkdir()
    fixture=Path(__file__).parent/'fixtures/cycle135-visit-review.zip'
    restore_checkpoint(fixture,folder/'research.sqlite');(folder/'case-info.json').write_text(json.dumps(dict(title='Old synthetic fixture',synthetic_example=True)))
    transition(w,cid,'define');before=w.view(cid)
    result=w.frame_draft(cid,'V5',before['revision'])
    assert result['record']['problem']=='Identify what remains unknown about the example'
    assert result['target_visit_id']=='V8' and result['persisted'] is False and result['approval_granted'] is False
    assert w.view(cid)==before
