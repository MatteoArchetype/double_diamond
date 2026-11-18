"""Cross-feature safety checks. All evidence and approvals here are simulated."""
import copy
import pytest
from dd_research_runtime.local_app import Workspace
from test_frame_revision import prepare_workspace, transition
from test_local_app import request
from test_claim_revision_interface import revision


@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace')
    cid=prepare_workspace(w)
    return w,cid


def restore(w,cid):
    data,_=w.backup(cid,w.view(cid)['revision'])
    inspected=w.inspect_backup(data)
    result=w.restore_backup(data,inspected['checkpoint_digest'])
    assert result['approval_granted'] is False
    return Workspace(w.path),result['case_id']


@pytest.mark.parametrize('recovered',[False,True])
@pytest.mark.parametrize('approved_before_edit',[False,True])
def test_old_transition_cannot_advance_revised_interpretation(case,recovered,approved_before_edit):
    w,cid=case
    transition(w,cid,'define')
    record=w.frame_draft(cid,'V2',w.view(cid)['revision'])['record']
    request(w,cid,'phase_record',dict(record=record,rationale='Simulated reconsideration of unchanged frame'))
    request(w,cid,'propose_transition',dict(target='develop',rationale='Synthetic transition review'),request_id='old-transition')
    if approved_before_edit:
        request(w,cid,'decide_gate',dict(gate_id='gate-old-transition',decision='approve',rationale='Simulated decision before interpretation changed'))
    request(w,cid,'claim_revision',revision(evidence_ids=['synthetic-synthetic-source'],uncertainty_ids=['linked-gap']))
    if recovered:w,cid=restore(w,cid)
    else:w=Workspace(w.path)
    if not approved_before_edit:
        # An exact old proposal can be decided, but it cannot authorize changed research.
        request(w,cid,'decide_gate',dict(gate_id='gate-old-transition',decision='approve',rationale='Simulated review of old proposal only'))
    before=w.view(cid)
    with pytest.raises((ValueError,PermissionError)):
        request(w,cid,'apply_gate',dict(gate_id='gate-old-transition',rationale='Attempt stale application'))
    assert w.view(cid)==before
    assert before['state']['workflow']['phase']=='define'
    assert before['currency']['define'] is False
    # Saved findings are immutable: a separately reviewed revisit is required first.
    immutable=w.view(cid)
    with pytest.raises(ValueError,match='immutable'):
        request(w,cid,'phase_record',dict(record=record,rationale='Cannot overwrite the prior finding'))
    assert w.view(cid)==immutable
    transition(w,cid,'define')
    # Recording the frame in a new visit cannot renew an old transition approval.
    request(w,cid,'phase_record',dict(record=record,rationale='Explicit simulated reassessment after interpretation revision'))
    reassessed=w.view(cid)
    assert reassessed['currency']['define'] is True
    with pytest.raises(PermissionError):
        request(w,cid,'apply_gate',dict(gate_id='gate-old-transition',rationale='Old approval remains content-bound'))
    assert w.view(cid)==reassessed
    transition(w,cid,'develop')
    final=w.view(cid)
    assert final['state']['workflow']['phase']=='develop'
    assert final['state']['human_gates']['gate-old-transition']['status']=='approved'
    assert final['state']['evidence']==before['state']['evidence']
    assert final['ledger_revision']==before['ledger_revision']


@pytest.mark.parametrize('recovered',[False,True])
def test_revised_interpretation_cannot_reuse_old_material_reframing_approval(case,recovered):
    w,cid=case
    transition(w,cid,'define')
    proposed=w.frame_draft(cid,'V2',w.view(cid)['revision'])['record']
    proposed['problem']='SYNTHETIC: a deliberately revised bounded question.'
    request(w,cid,'phase_record',dict(record=proposed,rationale='Simulated frame proposal'),request_id='old-frame')
    request(w,cid,'decide_gate',dict(gate_id='gate-old-frame',decision='approve',rationale='Simulated exact-content decision'))
    request(w,cid,'claim_revision',revision(evidence_ids=['synthetic-synthetic-source'],uncertainty_ids=['linked-gap']))
    if recovered:w,cid=restore(w,cid)
    else:w=Workspace(w.path)
    before=w.view(cid)
    with pytest.raises(PermissionError):
        request(w,cid,'apply_gate',dict(gate_id='gate-old-frame',rationale='Attempt approval against changed interpretation'))
    assert w.view(cid)==before
    assert before['state']['workflow']['visits'][-1]['record'] is None
    request(w,cid,'phase_record',dict(record=proposed,rationale='New proposal for revised research context'),request_id='new-frame')
    pending=w.view(cid)
    assert pending['state']['human_gates']['gate-new-frame']['status']=='pending_review'
    with pytest.raises(PermissionError):
        request(w,cid,'apply_gate',dict(gate_id='gate-new-frame',rationale='No approval inferred'))
    assert w.view(cid)==pending
    request(w,cid,'decide_gate',dict(gate_id='gate-new-frame',decision='approve',rationale='New simulated exact review'))
    request(w,cid,'apply_gate',dict(gate_id='gate-new-frame',rationale='Explicit new simulated application'))
    assert w.view(cid)['state']['workflow']['records']['define']==proposed


def test_multiple_revisions_and_recovery_keep_each_original_source_context(case):
    w,cid=case
    before=w.view(cid)
    visits={v['visit_id']:copy.deepcopy(w.visit(cid,v['visit_id'])) for v in before['state']['workflow']['visits']}
    request(w,cid,'claim_revision',revision(claim='SYNTHETIC: first bounded revision.',evidence_ids=['synthetic-synthetic-source'],uncertainty_ids=['linked-gap']))
    request(w,cid,'claim_revision',revision(claim='SYNTHETIC: unsupported hypothesis, not a finding.',evidence_ids=[],uncertainty_ids=[]))
    w,cid=restore(w,cid)
    final=w.view(cid)
    claim=final['state']['claims']['claim-interpretation']
    assert claim['evidence_origin']=='none' and claim['status']=='draft' and claim['disposition']=='unresolved'
    assert [h['previous']['claim'] for h in claim['belief_history']]==['SYNTHETIC: this interpretation remains tentative.','SYNTHETIC: first bounded revision.']
    assert claim['belief_history'][1]['previous']['evidence_ids']==['synthetic-synthetic-source']
    for vid,original in visits.items():
        historical=w.visit(cid,vid)
        assert historical['visit']==original['visit']
        assert historical['context']==original['context']
    for key in ('sources','evidence','workflow','human_gates','outputs','uncertainties'):
        assert final['state'][key]==before['state'][key]
    assert all(e['synthetic'] for e in final['state']['evidence'].values())
    assert not any(r['current'] for r in final['reports'])
