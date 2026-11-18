"""Learning examples remain synthetic and publish only as complete cases."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from dd_research_runtime.local_app import Workspace
from test_local_app import create


def assert_example(w,cid):
    view=w.view(cid)
    assert view['meta']['synthetic_example'] is True
    assert view['state']['workflow']['workflow_version']==3
    assert view['state']['evidence'] and all(e['synthetic'] is True for e in view['state']['evidence'].values())
    assert view['reports'][0]['current'] is True
    assert not any(r.get('publication_authorized') for r in view['state']['outputs'].values())
    assert not view['state'].get('acceptance_records')
    assert all(not a['execution_authorized'] for a in view['agendas'])
    assert view['guidance']['synthetic_example'] is True
    return view


@pytest.mark.parametrize('phase',['after_example','before_reservation','before_publication'])
def test_example_error_leaves_existing_research_unchanged(tmp_path,phase):
    w=Workspace(tmp_path/'workspace');existing=create(w);before=w.view(existing)
    def fault(name):
        if name==phase:raise RuntimeError('simulated example interruption')
    with pytest.raises(RuntimeError):w.demo(_fault=fault)
    assert [c['case_id'] for c in w.cases()]==[existing]
    assert w.view(existing)==before
    assert list(w.path.iterdir())==[w.case_path(existing)]


def test_example_lost_response_keeps_complete_synthetic_case(tmp_path):
    w=Workspace(tmp_path/'workspace')
    def fault(name):
        if name=='after_publication':raise RuntimeError('simulated lost response')
    with pytest.raises(RuntimeError):w.demo(_fault=fault)
    cases=w.cases();assert len(cases)==1
    assert_example(Workspace(w.path),cases[0]['case_id'])
    assert not any(p.name.startswith('.example-') for p in w.path.iterdir())


def test_partial_example_builder_failure_is_never_published(tmp_path,monkeypatch):
    from dd_research_runtime import agenda_demo
    w=Workspace(tmp_path/'workspace')
    def fail(folder):
        folder.mkdir();(folder/'research.sqlite').write_bytes(b'partial fixture')
        raise RuntimeError('simulated builder failure')
    monkeypatch.setattr(agenda_demo,'run_demo',fail)
    with pytest.raises(RuntimeError):w.demo()
    assert w.cases()==[] and list(w.path.iterdir())==[]


def test_parallel_examples_publish_distinct_complete_cases(tmp_path):
    w=Workspace(tmp_path/'workspace')
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:w.demo(),range(2)))
    assert len(set(ids))==2 and {c['case_id'] for c in w.cases()}==set(ids)
    for cid in ids:assert_example(w,cid)


def test_example_identifier_collision_preserves_existing_case(tmp_path,monkeypatch):
    from dd_research_runtime import local_app
    w=Workspace(tmp_path/'workspace');cid=create(w);before=w.view(cid)
    monkeypatch.setattr(local_app,'_id',lambda:cid)
    with pytest.raises(FileExistsError):w.demo()
    assert w.view(cid)==before and len(w.cases())==1
    assert list(w.path.iterdir())==[w.case_path(cid)]


@pytest.mark.parametrize('change',[{'fixture_only':False},{'live_sources_used':True},{'mvp_ready':True}])
def test_example_summary_cannot_claim_real_sources_or_acceptance(tmp_path,monkeypatch,change):
    from dd_research_runtime import agenda_demo
    w=Workspace(tmp_path/'workspace');original=agenda_demo.run_demo
    def changed(folder):
        result=original(folder);result.update(change);return result
    monkeypatch.setattr(agenda_demo,'run_demo',changed)
    with pytest.raises(ValueError,match='synthetic fixture'):w.demo()
    assert w.cases()==[] and list(w.path.iterdir())==[]


@pytest.mark.parametrize('phase',['after_example','before_publication','after_publication'])
def test_abrupt_example_exit_leaves_no_listed_partial_case(tmp_path,phase):
    path=tmp_path/'workspace'
    program='''import os,sys
from dd_research_runtime.local_app import Workspace
w=Workspace(sys.argv[1])
def fault(name):
    if name==sys.argv[2]:os._exit(73)
w.demo(_fault=fault)
'''
    result=subprocess.run([sys.executable,'-c',program,str(path),phase],cwd=Path(__file__).parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==73,result.stderr
    w=Workspace(path);cases=w.cases()
    assert len(cases)==(1 if phase=='after_publication' else 0)
    if cases:assert_example(w,cases[0]['case_id'])
    # Remnants stay private or empty, never adopted into research history.
    if not cases:
        for p in path.iterdir():
            if len(p.name)==32:assert list(p.iterdir())==[]
    cid=create(w);assert w.view(cid)['state']['workflow']['phase']=='discover'


def test_example_visibility_and_metadata_privacy_at_publication(tmp_path):
    w=Workspace(tmp_path/'workspace');seen=[]
    def inspect(phase):
        assert len(w.cases())==(1 if phase=='after_publication' else 0)
        seen.append(phase)
    cid=w.demo(_fault=inspect)
    assert seen==['after_example','before_reservation','before_publication','after_publication']
    assert w.case_path(cid).stat().st_mode&0o777==0o700
    assert (w.case_path(cid)/'case-info.json').stat().st_mode&0o777==0o600
    assert_example(w,cid)
