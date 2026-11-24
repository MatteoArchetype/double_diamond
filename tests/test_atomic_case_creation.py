"""Publish complete new cases; all questions and failures are synthetic fixtures."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from dd_research_runtime.local_app import Workspace
from test_local_app import create


def data():return dict(title='Synthetic atomic creation',question='What remains unknown in this invented example?',scope='Synthetic verification only',max_visits=8,max_alternatives=3)


@pytest.mark.parametrize('phase',['after_initialize','after_workflow','before_reservation','before_publication'])
def test_failed_creation_never_exposes_a_partial_case(tmp_path,phase):
    w=Workspace(tmp_path/'workspace');existing=create(w);before=w.view(existing)
    def fault(name):
        if name==phase:raise RuntimeError('simulated interruption')
    with pytest.raises(RuntimeError):w.create(data(),_fault=fault)
    assert [c['case_id'] for c in w.cases()]==[existing]
    assert list(w.path.iterdir())==[w.case_path(existing)]
    assert w.view(existing)==before


def test_uncertain_response_after_publication_retains_complete_discover_case(tmp_path):
    w=Workspace(tmp_path/'workspace')
    def fault(name):
        if name=='after_publication':raise RuntimeError('simulated lost response')
    with pytest.raises(RuntimeError):w.create(data(),_fault=fault)
    cases=Workspace(w.path).cases();assert len(cases)==1
    view=w.view(cases[0]['case_id']);assert view['revision']==1 and view['ledger_revision']==0
    assert view['state']['workflow']['phase']=='discover' and not view['state']['workflow']['records']
    for key in ('evidence','claims','human_gates'):assert not view['state'][key]
    assert not any(p.name.startswith('.create-') for p in w.path.iterdir())


def test_parallel_creations_publish_distinct_complete_cases(tmp_path):
    w=Workspace(tmp_path/'workspace')
    with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(lambda _:w.create(data()),range(8)))
    assert len(set(ids))==8 and {c['case_id'] for c in w.cases()}==set(ids)
    for cid in ids:
        view=w.view(cid);assert view['revision']==1 and view['state']['workflow']['workflow_id']==cid
        assert not view['state']['human_gates']


def test_identifier_collision_never_overwrites_an_existing_case(tmp_path,monkeypatch):
    from dd_research_runtime import local_app
    w=Workspace(tmp_path/'workspace');cid=create(w);before=w.view(cid)
    monkeypatch.setattr(local_app,'_id',lambda:cid)
    with pytest.raises(FileExistsError):w.create(data())
    assert w.view(cid)==before and len(w.cases())==1
    assert not any(p.name.startswith('.create-') for p in w.path.iterdir())


@pytest.mark.parametrize('phase',['after_initialize','after_workflow','before_publication','after_publication'])
def test_process_exit_recovers_as_absent_or_complete_case(tmp_path,phase):
    path=tmp_path/'workspace'
    program='''import os,sys,json
from dd_research_runtime.local_app import Workspace
w=Workspace(sys.argv[1])
def fault(name):
    if name==sys.argv[2]:os._exit(73)
w.create(json.loads(sys.argv[3]),_fault=fault)
'''
    result=subprocess.run([sys.executable,'-c',program,str(path),phase,json.dumps(data())],cwd=Path(__file__).parents[1],capture_output=True,text=True,timeout=30)
    assert result.returncode==73,result.stderr
    w=Workspace(path);cases=w.cases()
    assert len(cases)==(1 if phase=='after_publication' else 0)
    if cases:
        cid=cases[0]['case_id'];view=w.view(cid)
        assert view['revision']==1 and view['ledger_revision']==0 and view['state']['workflow']['phase']=='discover'
        assert view['meta']==dict(title=data()['title'],synthetic_example=False)
    # Crash remnants are private staging/empty reservations, never adopted or auto-deleted.
    for p in path.iterdir():
        if len(p.name)==32 and not cases:assert list(p.iterdir())==[]
    new=w.create(data());assert w.view(new)['state']['workflow']['phase']=='discover'


def test_validation_precedes_any_case_directory(tmp_path):
    w=Workspace(tmp_path/'workspace');bad=data();bad['max_visits']=3
    with pytest.raises(ValueError):w.create(bad)
    assert list(w.path.iterdir())==[]


def test_staged_case_is_not_listed_before_publication(tmp_path):
    w=Workspace(tmp_path/'workspace');seen=[]
    def inspect(phase):
        if phase!='after_publication':assert w.cases()==[]
        else:assert len(w.cases())==1
        seen.append(phase)
    cid=w.create(data(),_fault=inspect)
    assert seen==['after_initialize','after_workflow','before_reservation','before_publication','after_publication']
    if os.name!='nt':  # Windows has no POSIX modes; chmod only toggles read-only.
        assert w.case_path(cid).stat().st_mode&0o777==0o700
        assert (w.case_path(cid)/'case-info.json').stat().st_mode&0o777==0o600
