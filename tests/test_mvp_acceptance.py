import json
import subprocess
import sys
from pathlib import Path

import pytest
from dd_research_runtime.mvp_demo import run_demo
from dd_research_runtime.runtime import ResearchState,GateRequired
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.pending_retrieval import PendingRetrievalQueue
from dd_research_runtime.checkpoints import inspect_checkpoint

ROOT=Path(__file__).resolve().parents[1]


def test_offline_fixture_checks_and_honest_mvp_status(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    report=run_demo()
    assert report['fixture_only'] and report['live_sources_used'] is False
    assert report['reviewer_identity'] == 'simulated fixture callback'
    assert all(report['checks'].values())
    assert report['mvp_ready'] is False
    assert list(tmp_path.iterdir()) == []
    blockers={c['id'] for c in report['criteria'] if c['status'] != 'fixture_verified'}
    assert blockers == {'MVP-08'}


def test_kept_fixture_reopens_without_real_source_claims(tmp_path):
    path=tmp_path/'new-fixture'
    report=run_demo(path)
    stored=json.loads((path/'demo-report.json').read_text())
    assert stored == report
    store=PersistentEvidenceStore(path/'fixture.sqlite')
    state,revision=store.load()
    assert revision == 24 and state.sources == {}
    assert state.workflow['status']=='stopped' and 'fixture-research-report' in state.outputs
    assert (path/'research-draft.md').is_file()
    assert set(state.claims) == {'fixture-claim','fixture-alternative'} and 'detached-example' not in state.claims
    assert all(e['synthetic'] is True for e in state.evidence.values())
    assert state.human_gates['publication']['status'] == 'pending_review'
    assert PendingRetrievalQueue(store).load('fixture-candidate').status == 'committed'
    assert inspect_checkpoint(path/'fixture-checkpoint.zip')['summary'] == report['checkpoint_summary']
    assert PersistentEvidenceStore(path/'restored.sqlite').load()[0].snapshot() == state.snapshot()


def test_existing_demo_destination_preserved(tmp_path):
    path=tmp_path/'exists';path.mkdir();(path/'marker').write_text('keep')
    with pytest.raises(FileExistsError):run_demo(path)
    assert (path/'marker').read_text() == 'keep'
    assert sorted(p.name for p in path.iterdir()) == ['marker']


def test_real_subprocess_demo_runs_from_package():
    result=subprocess.run([sys.executable,'-m','dd_research_runtime.mvp_demo'],cwd=ROOT,text=True,capture_output=True,timeout=20)
    assert result.returncode == 0 and result.stderr == ''
    report=json.loads(result.stdout)
    assert report['mvp_ready'] is False and report['checks']['all_fixture_invariants'] is True


def test_demo_cli_does_not_overwrite_existing_directory(tmp_path):
    target=tmp_path/'existing';target.mkdir();(target/'marker').write_text('keep')
    result=subprocess.run([sys.executable,'-m','dd_research_runtime.mvp_demo','--keep',str(target)],cwd=ROOT,text=True,capture_output=True,timeout=20)
    assert result.returncode == 1 and result.stdout == ''
    assert json.loads(result.stderr)['ok'] is False
    assert (target/'marker').read_text() == 'keep'


def test_contract_has_finite_required_criteria_and_covered_blockers():
    contract=json.loads((ROOT/'MVP_ACCEPTANCE.json').read_text())
    ids=[c['id'] for c in contract['criteria']]
    assert len(ids) == len(set(ids)) == 8
    planned={cid for cycle in contract['work_plan'] for cid in cycle['criteria']}
    unresolved={c['id'] for c in contract['criteria'] if c['status'] != 'fixture_verified'}
    assert planned == unresolved
    for cycle in contract['work_plan']:
        assert set(cycle['depends_on']) <= set(ids)
    assert 'not guaranteed' in contract['estimate']


@pytest.mark.parametrize('gate_type,action',[
    ('primary_research','publication'),('publication','phase_transition'),
    ('sensitive_access','consequential_action'),
])
def test_approved_gate_cannot_authorize_a_different_action(gate_type,action):
    state=ResearchState()
    state.create_gate('gate',gate_type,'Proposal','Reason','Approve')
    state.approve_gate('gate')
    before=state.snapshot()
    with pytest.raises(GateRequired,match='type must match'):state.execute_gated('gate',action)
    assert state.snapshot() == before


@pytest.mark.parametrize('gate_type',['publication','primary_research'])
def test_matching_gate_executes_once(gate_type):
    state=ResearchState()
    state.create_gate('gate',gate_type,'Proposal','Reason','Approve')
    state.approve_gate('gate');state.execute_gated('gate',gate_type)
    assert state.human_gates['gate']['status'] == 'executed'
    with pytest.raises(GateRequired):state.execute_gated('gate',gate_type)


def test_legacy_gate_missing_type_does_not_authorize_publication():
    state=ResearchState(human_gates={'legacy':dict(status='approved')})
    with pytest.raises(GateRequired,match='type must match'):state.execute_gated('legacy','publication')
    assert state.human_gates['legacy']['status'] == 'approved'


def test_missing_fixture_permission_does_not_report_success(monkeypatch):
    import dd_research_runtime.mvp_demo as demo
    monkeypatch.setattr(demo,'_fixture_authorize',lambda *_:False)
    with pytest.raises(PermissionError):run_demo()
