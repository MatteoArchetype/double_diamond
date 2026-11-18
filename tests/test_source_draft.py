from concurrent.futures import ThreadPoolExecutor

import pytest

from dd_research_runtime.local_app import Workspace
from dd_research_runtime.source_draft import DRAFT_FIELDS
from test_local_app import create


def draft():
    return dict.fromkeys(DRAFT_FIELDS,'') | {'title':'Draft source','passage':'Unfinished excerpt','synthetic':True}


def test_source_draft_survives_reopen_without_approving_evidence(tmp_path):
    workspace=Workspace(tmp_path)
    case,other=create(workspace),create(workspace)
    before=workspace.view(case)
    assert workspace.source_draft(case).read()=={'version':0,'draft':None}
    saved=workspace.source_draft(case).write(0,draft())
    reopened=Workspace(tmp_path).source_draft(case)
    assert reopened.read()==saved
    assert workspace.source_draft(other).read()['draft'] is None
    assert workspace.view(case)==before
    assert reopened.write(saved['version'],None)=={'version':2,'draft':None}
    assert reopened.read()=={'version':2,'draft':None}


def test_draft_rejects_approval_fields_and_concurrent_overwrites(tmp_path):
    workspace=Workspace(tmp_path)
    case=create(workspace)
    with pytest.raises(ValueError):
        workspace.source_draft(case).write(0,dict(draft(),confirmed=True))
    def write(title):
        try:
            return workspace.source_draft(case).write(0,dict(draft(),title=title))
        except RuntimeError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        successes=[result for result in pool.map(write,['One','Two']) if result]
    assert len(successes)==1
    assert workspace.source_draft(case).read()==successes[0]


def test_discover_draft_is_separate_and_bound_to_open_visit(tmp_path):
    from test_local_app import request, source

    workspace=Workspace(tmp_path)
    case=create(workspace)
    request(workspace,case,'source',source(),request_id='discover-evidence')
    before=workspace.view(case)
    visit=before['state']['workflow']['visits'][-1]['visit_id']
    data=dict(notes='Unfinished observation',perspectives='Residents\n\nPlanners',limitations='',rationale='',
              evidence_ids=['synthetic-discover-evidence'])
    saved=workspace.discover_draft(case,visit).write(0,data)
    assert Workspace(tmp_path).discover_draft(case,visit).read()==saved
    assert workspace.source_draft(case).read()['draft'] is None
    assert workspace.view(case)==before
    with pytest.raises(RuntimeError,match='no longer open'):
        workspace.discover_draft(case,'V2')
    request(workspace,case,'phase_record',dict(
        rationale='Explicit simulated save',
        record=dict(notes='Recorded observation',perspectives=['Residents','Planners'],limitations='Fixture',
                    evidence_ids=data['evidence_ids'])
    ))
    with pytest.raises(RuntimeError,match='no longer open'):
        workspace.discover_draft(case,visit)


def test_define_draft_restores_frame_fields_without_record_or_gate(tmp_path):
    from test_local_app import request, source

    workspace=Workspace(tmp_path)
    case=create(workspace)
    request(workspace,case,'source',source(),request_id='fixture')
    request(workspace,case,'phase_record',dict(
        rationale='Simulated Discover record',
        record=dict(notes='Recorded observation',perspectives=['Residents','Planners'],limitations='Fixture',
                    evidence_ids=['synthetic-fixture'])
    ))
    with pytest.raises(RuntimeError,match='no longer open'):
        workspace.define_draft(case,'V1')
    request(workspace,case,'propose_transition',dict(target='define',rationale='Simulated transition'),request_id='define')
    request(workspace,case,'decide_gate',dict(gate_id='gate-define',decision='approve',rationale='Simulated approval'))
    request(workspace,case,'apply_gate',dict(gate_id='gate-define',rationale='Simulated application'))
    before=workspace.view(case)
    data=dict(problem='Unfinished frame',criteria='First criterion\n\nSecond criterion',
              rationale='',claim_ids=[],uncertainty_ids=[])
    saved=workspace.define_draft(case,'V2').write(0,data)
    assert Workspace(tmp_path).define_draft(case,'V2').read()==saved
    assert workspace.view(case)==before
    with pytest.raises(ValueError):
        workspace.define_draft(case,'V2').write(saved['version'],dict(data,approved=True))
    with pytest.raises(RuntimeError,match='no longer open'):
        workspace.discover_draft(case,'V2')


@pytest.mark.parametrize('phase,record', [
    ('develop', {'alternatives':[
        dict(alternative_id='option-1',hypothesis='First',test='',limitations='',claim_ids=[],evidence_ids=[]),
        dict(alternative_id='option-2',hypothesis='',test='',limitations='',claim_ids=[],evidence_ids=[]),
    ]}),
    ('deliver', dict(selected_alternative_id='option-1',decision='stop_unresolved',summary='',limitations='',claim_ids=[],
        evaluations=[dict(evaluation_id='evaluation-1',alternative_id='option-1',method='',outcome='inconclusive',
                          limitations='',evidence_ids=['passage'])],
        criterion_assessments=[dict(criterion_index=0,outcome='unknown',rationale='',next_research='',
                                    evaluation_ids=['evaluation-1'])])),
])
def test_later_phase_drafts_reopen_incomplete_rows_and_reject_approval(tmp_path,phase,record):
    from dd_research_runtime.source_draft import DeliverDraft, DevelopDraft
    draft_type={'develop':DevelopDraft,'deliver':DeliverDraft}[phase]
    path=tmp_path/'draft.sqlite'
    data=dict(record=record,rationale='Unfinished notes')
    saved=draft_type(path).write(0,data)
    assert draft_type(path).read()==saved
    with pytest.raises(ValueError):
        draft_type(path).write(saved['version'],dict(data,confirmed=True))
    assert draft_type(path).read()==saved
    workspace=Workspace(tmp_path/'cases')
    with pytest.raises(RuntimeError,match='no longer open'):
        workspace.later_phase_draft(create(workspace),'V1',phase)
