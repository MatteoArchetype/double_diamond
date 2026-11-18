"""Checkpoint transport uses synthetic fixtures, never actual human acceptance."""
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from dd_research_runtime.local_app import Workspace,Handler
from dd_research_runtime import interface_backups as backups
from test_local_app import create,request,source,FakeServer

@pytest.fixture
def saved(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w)
    request(w,cid,'source',source(),request_id='fixture')
    request(w,cid,'propose_transition',dict(target='discover',rationale='Simulated review'),request_id='pending')
    before=w.view(cid);data,_=w.backup(cid,before['revision'])
    return w,cid,before,data

def test_round_trip_preserves_exact_state_and_pending_human_gate(saved):
    w,cid,before,data=saved;preview=w.inspect_backup(data)
    assert preview['integrity_verified'] and not preview['identity_authenticated'] and not preview['approval_granted']
    assert preview['evidence_counts']==dict(synthetic=1,source_records=0)
    assert preview['historical_gate_counts']=={'pending_review':1}
    result=w.restore_backup(data,preview['checkpoint_digest']);after=w.view(result['case_id'])
    assert after['state']==before['state']
    assert (after['revision'],after['ledger_revision'])==(before['revision'],before['ledger_revision'])
    assert w.view(cid)==before and result['case_id']!=cid
    assert not result['approval_granted']
    meta=json.loads((w.path/result['case_id']/'case-info.json').read_text())
    assert meta['synthetic_only'] and meta['restored_checkpoint'] and not meta['synthetic_example']
    with pytest.raises(PermissionError):request(w,result['case_id'],'apply_gate',dict(gate_id='gate-pending',rationale='Still unapproved'))

def test_inspection_does_not_publish_a_case(saved):
    w,cid,before,data=saved;paths=set(w.path.iterdir());w.inspect_backup(data)
    assert set(w.path.iterdir())==paths and w.view(cid)==before

@pytest.mark.parametrize('revision',[True,False,None,-1,'2',1.2])
def test_revision_required(saved,revision):
    w,cid,before,data=saved
    with pytest.raises(ValueError):w.backup(cid,revision)
    assert w.view(cid)==before

def test_stale_backup_refused_without_mutation(saved):
    w,cid,before,data=saved
    with pytest.raises(RuntimeError,match='changed'):w.backup(cid,before['revision']-1)
    assert w.view(cid)==before

@pytest.mark.parametrize('digest',['','x'*64,'a'*64,None,42])
def test_restore_requires_exact_inspected_file(saved,digest):
    w,cid,before,data=saved
    with pytest.raises(ValueError):w.restore_backup(data,digest)
    assert len(w.cases())==1 and w.view(cid)==before

@pytest.mark.parametrize('payload',[b'',b'not a zip',b'PK',None,'bad'])
def test_invalid_upload_never_publishes(saved,payload):
    w,cid,before,data=saved
    with pytest.raises((ValueError,TypeError)):w.inspect_backup(payload)
    assert len(w.cases())==1 and w.view(cid)==before

def test_size_limit_before_parsing(saved,monkeypatch):
    w,cid,before,data=saved;monkeypatch.setattr(backups,'MAX_TRANSFER_BYTES',len(data)-1)
    with pytest.raises(ValueError,match='32 MiB'):w.inspect_backup(data)
    with pytest.raises(ValueError,match='32 MiB'):w.backup(cid,before['revision'])

@pytest.mark.parametrize('point',['after_verification','before_publication','after_publication'])
def test_interruption_leaves_only_absent_or_complete_case(saved,point):
    w,cid,before,data=saved
    def fault(name):
        if name==point:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):backups.restore_upload(w.path,data,expected_digest=hashlib.sha256(data).hexdigest(),_fault=fault)
    cases=w.cases();assert len(cases)==(2 if point=='after_publication' else 1)
    for case in cases:assert w.view(case['case_id'])['state']==before['state']
    assert w.view(cid)==before and not list(w.path.glob('.restore-*'))

@pytest.mark.parametrize('point',['before_publication','after_publication'])
def test_process_death_reopens_only_complete_cases(saved,tmp_path,point):
    w,cid,before,data=saved;archive=tmp_path/'fixture.zip';archive.write_bytes(data)
    script="""import os,sys,hashlib
from pathlib import Path
from dd_research_runtime.interface_backups import restore_upload
data=Path(sys.argv[2]).read_bytes()
def fault(name):
 if name==sys.argv[3]:os._exit(73)
restore_upload(sys.argv[1],data,expected_digest=hashlib.sha256(data).hexdigest(),_fault=fault)
"""
    result=subprocess.run([sys.executable,'-c',script,str(w.path),str(archive),point])
    assert result.returncode==73
    reopened=Workspace(w.path);assert len(reopened.cases())==(2 if point=='after_publication' else 1)
    assert reopened.view(cid)==before
    for case in reopened.cases():assert reopened.view(case['case_id'])['state']==before['state']

def test_concurrent_restores_publish_distinct_complete_copies(saved):
    w,cid,before,data=saved;digest=hashlib.sha256(data).hexdigest()
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:w.restore_backup(data,digest),range(3)))
    assert len({r['case_id'] for r in results})==3 and len(w.cases())==4
    for result in results:assert w.view(result['case_id'])['state']==before['state']
    assert w.view(cid)==before

def test_existing_case_collision_cannot_overwrite(saved,monkeypatch):
    w,cid,before,data=saved;monkeypatch.setattr(backups.uuid,'uuid4',lambda:SimpleNamespace(hex=cid))
    with pytest.raises(FileExistsError):w.restore_backup(data,hashlib.sha256(data).hexdigest())
    assert w.view(cid)==before

def handler(w,path,body=b'',**headers):
    h=object.__new__(Handler);server=FakeServer();server.workspace=w;server.mutation_lock=threading.Lock()
    h.server=server;h.path=path;h.rfile=io.BytesIO(body)
    h.headers=dict(Host='127.0.0.1:12345',Origin=server.origin,Authorization='Bearer private-token',**headers)
    responses=[];h._reply=lambda *args,**kwargs:responses.append((args,kwargs))
    return h,responses

def test_http_download_inspect_restore(saved):
    w,cid,before,data=saved
    h,responses=handler(w,f'/api/checkpoint?case={cid}&revision={before["revision"]}');h.do_GET()
    assert responses[0][0][0]==200 and responses[0][0][2]=='application/zip'
    h,responses=handler(w,'/api/checkpoint/inspect',data,**{'Content-Type':'application/zip','Content-Length':str(len(data))});h.do_POST()
    assert responses[0][0][0]==200
    h,responses=handler(w,'/api/checkpoint/restore',data,**{'Content-Type':'application/zip','Content-Length':str(len(data)),'X-Checkpoint-SHA256':hashlib.sha256(data).hexdigest()});h.do_POST()
    assert responses[0][0][0]==201 and len(w.cases())==2

@pytest.mark.parametrize('changes',[
 {'Content-Type':'application/json'}, {'Content-Length':'33554433'}, {'Transfer-Encoding':'chunked'},
 {'Content-Length':'0'}, {'Content-Length':'999999'}, {'Origin':'https://evil.test'}, {'Authorization':'Bearer wrong'}])
def test_http_bad_upload_does_not_mutate(saved,changes):
    w,cid,before,data=saved;headers={'Content-Type':'application/zip','Content-Length':str(len(data))};headers.update(changes)
    # Override security fields after constructing the handler.
    security={k:headers.pop(k) for k in list(headers) if k in ('Origin','Authorization')}
    h,responses=handler(w,'/api/checkpoint/restore',data,**headers);h.headers.update(security);h.do_POST()
    assert responses[0][0][0] in (400,403) and len(w.cases())==1 and w.view(cid)==before
