"""Read-only guidance never promotes historical approvals to current permission."""
import copy
import pytest
from dd_research_runtime.local_app import Workspace
from dd_research_runtime.interface_guidance import research_gate_contexts
from test_frame_revision import prepare_workspace,transition
from test_local_app import request
from test_claim_revision_interface import revision


@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=prepare_workspace(w)
    transition(w,cid,'define')
    return w,cid


def propose(w,cid,kind):
    if kind=='phase_transition':
        record=w.frame_draft(cid,'V2',w.view(cid)['revision'])['record']
        request(w,cid,'phase_record',dict(record=record,rationale='Simulated reconsideration'))
        request(w,cid,'propose_transition',dict(target='develop',rationale='Simulated review'),request_id='context')
    else:
        record=w.frame_draft(cid,'V2',w.view(cid)['revision'])['record'];record['problem']='SYNTHETIC: narrower question.'
        request(w,cid,'phase_record',dict(record=record,rationale='Simulated reframing proposal'),request_id='context')


def revise(w,cid):
    request(w,cid,'claim_revision',revision(evidence_ids=['synthetic-synthetic-source'],uncertainty_ids=['linked-gap']))


@pytest.mark.parametrize('kind',['phase_transition','material_reframing'])
@pytest.mark.parametrize('status',['pending_review','approved'])
@pytest.mark.parametrize('recovery',[False,True])
def test_changed_research_reviews_are_historical_not_next_work(case,kind,status,recovery):
    w,cid=case;propose(w,cid,kind)
    if status=='approved':request(w,cid,'decide_gate',dict(gate_id='gate-context',decision='approve',rationale='Simulated approval'))
    before=w.view(cid)
    assert before['gate_context_current']['gate-context'] is True
    assert before['guidance']['step']==('review_pending' if status=='pending_review' else 'apply_separately')
    revise(w,cid)
    saved=w.view(cid);gate=copy.deepcopy(saved['state']['human_gates']['gate-context'])
    if recovery:
        data,_=w.backup(cid,saved['revision']);preview=w.inspect_backup(data);result=w.restore_backup(data,preview['checkpoint_digest']);assert result['approval_granted'] is False;cid=result['case_id']
    w=Workspace(w.path);snapshot=w.store(cid).load()[0].snapshot();view=w.view(cid)
    assert view['gate_context_current']['gate-context'] is False
    assert view['state']['human_gates']['gate-context']==gate and gate['status']==status
    assert view['guidance']['research_reviews_pending']==view['guidance']['approved_changes_unapplied']==0
    assert view['guidance']['outdated_research_reviews']==1
    assert view['guidance']['step']==('review_changed_basis' if kind=='phase_transition' else 'record_define')
    assert view['guidance']['execution_authorized'] is False
    assert w.store(cid).load()[0].snapshot()==snapshot


def test_new_matching_proposal_wins_over_old_historical_approval(case):
    w,cid=case;propose(w,cid,'phase_transition')
    request(w,cid,'decide_gate',dict(gate_id='gate-context',decision='approve',rationale='Simulated old approval'))
    revise(w,cid)
    request(w,cid,'propose_transition',dict(target='define',rationale='Revisit changed synthetic context'),request_id='fresh')
    view=w.view(cid)
    assert view['guidance']['step']=='review_pending' and view['guidance']['research_reviews_pending']==1
    assert view['guidance']['outdated_research_reviews']==1
    assert view['gate_context_current']['gate-fresh'] is True
    assert view['gate_context_current']['gate-context'] is False
    before=view['state']['human_gates']['gate-context']
    request(w,cid,'decide_gate',dict(gate_id='gate-fresh',decision='approve',rationale='Simulated fresh review'))
    view=w.view(cid)
    assert view['guidance']['step']=='apply_separately' and view['guidance']['approved_changes_unapplied']==1
    request(w,cid,'apply_gate',dict(gate_id='gate-fresh',rationale='Explicit simulated revisit'))
    assert w.view(cid)['state']['human_gates']['gate-context']==before


def test_pending_outdated_review_can_be_explicitly_rejected_without_research_change(case):
    w,cid=case;propose(w,cid,'material_reframing');revise(w,cid);before=w.view(cid)
    request(w,cid,'decide_gate',dict(gate_id='gate-context',decision='reject',rationale='Simulated explicit rejection of superseded context'))
    after=w.view(cid)
    assert after['state']['human_gates']['gate-context']['status']=='rejected'
    assert after['guidance']['outdated_research_reviews']==0
    for key in ('workflow','claims','sources','evidence'):assert after['state'][key]==before['state'][key]


def test_content_match_is_not_permission_and_ignores_other_gate_types(case):
    w,cid=case;propose(w,cid,'phase_transition');state=w.store(cid).load()[0]
    state.human_gates['external']=dict(gate_type='publication',status='approved')
    before=state.snapshot();contexts=research_gate_contexts(state)
    assert contexts['gate-context'] is True and 'external' not in contexts
    assert state.snapshot()==before
    # A legacy/missing binding fails closed rather than guessing currentness.
    state.human_gates['gate-context']['action']['payload'].pop('research_digest')
    assert research_gate_contexts(state)['gate-context'] is False
