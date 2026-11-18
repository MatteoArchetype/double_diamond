"""Local UI boundary tests. All reviews and evidence are test fixtures."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from dd_research_runtime.local_app import Workspace,Handler,CAPABILITIES
from test_research_agenda import prepare,item

@pytest.fixture
def workspace(tmp_path):return Workspace(tmp_path/'workspace')

def create(w):return w.create(dict(title='Synthetic test',question='What remains unknown?',scope='Test only',max_visits=8,max_alternatives=3))
def request(w,cid,action,data,**overrides):
    view=w.view(cid)
    body=dict(action=action,data=data,expected_revision=view['revision'],expected_ledger_revision=view['ledger_revision'],request_id=uuid.uuid4().hex)
    body.update(overrides);return w.action(cid,body)
def source(**overrides):
    data=dict(title='Synthetic fixture',publisher='Fixture',url='https://example.org/fixture',passage='Invented passage.',location='section 1',snapshot='Context. Invented passage. Context.',group='fixture',synthetic=True,confirmed=True,rationale='Explicit simulated review for testing')
    data.update(overrides);return data

def test_create_restart_and_boundaries(workspace):
    cid=create(workspace);view=Workspace(workspace.path).view(cid)
    assert view['state']['workflow']['phase']=='discover' and view['revision']==1
    assert not view['state']['human_gates']
    assert workspace.cases()[0]['case_id']==cid
    assert not {'publication','host_acceptance','gate_execute'} & CAPABILITIES

@pytest.mark.parametrize('bad',['../research','A'*32,'','0'*32,None])
def test_no_arbitrary_case_paths(workspace,bad):
    with pytest.raises(ValueError):workspace.view(bad)

@pytest.mark.parametrize('change',[{'confirmed':False},{'snapshot':'No matching passage'},{'synthetic':'false'},{'passage':''}])
def test_failed_source_review_has_no_partial_commit(workspace,change):
    cid=create(workspace);before=workspace.view(cid)
    with pytest.raises((ValueError,PermissionError)):request(workspace,cid,'source',source(**change))
    assert workspace.view(cid)==before

def test_source_synthetic_origin_and_exact_snapshot_survive_restart(workspace):
    cid=create(workspace);request(workspace,cid,'source',source(),request_id='intake')
    view=Workspace(workspace.path).view(cid)
    assert view['ledger_revision']==1 and view['revision']==2
    assert view['state']['evidence']['synthetic-intake']['synthetic'] is True
    assert view['state']['evidence']['synthetic-intake']['finding']=='Invented passage.'
    assert not view['state']['human_gates']

def test_stale_tabs_do_not_silently_repeat_writes(workspace):
    cid=create(workspace);request(workspace,cid,'source',source())
    before=workspace.view(cid)
    with pytest.raises(RuntimeError,match='changed'):request(workspace,cid,'source',source(),expected_revision=1,expected_ledger_revision=0)
    assert workspace.view(cid)==before

def test_propose_decide_apply_are_separate_and_rejection_preserves_phase(workspace):
    cid=create(workspace)
    request(workspace,cid,'propose_transition',dict(target='discover',rationale='Review the discovery approach'),request_id='proposal')
    assert workspace.view(cid)['state']['workflow']['visits'].__len__()==1
    with pytest.raises(PermissionError):request(workspace,cid,'apply_gate',dict(gate_id='gate-proposal',rationale='Not yet approved'))
    request(workspace,cid,'decide_gate',dict(gate_id='gate-proposal',decision='reject',rationale='Simulated rejection'))
    with pytest.raises(PermissionError):request(workspace,cid,'apply_gate',dict(gate_id='gate-proposal',rationale='Rejected'))
    request(workspace,cid,'propose_transition',dict(target='discover',rationale='Review discovery again'),request_id='second')
    request(workspace,cid,'decide_gate',dict(gate_id='gate-second',decision='approve',rationale='Simulated approval'))
    assert len(workspace.view(cid)['state']['workflow']['visits'])==1
    request(workspace,cid,'apply_gate',dict(gate_id='gate-second',rationale='Explicit simulated application'))
    assert len(workspace.view(cid)['state']['workflow']['visits'])==2

def test_reports_and_agendas_use_existing_verified_engine(workspace):
    cid=create(workspace)
    # A separate fixture case starts from a blank store, with no real source acceptance.
    import shutil
    shutil.rmtree(workspace.path/cid)
    folder=workspace.path/cid;folder.mkdir()
    from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
    from dd_research_runtime.runtime import ResearchState
    store=PersistentEvidenceStore(folder/'research.sqlite');store.initialize(ResearchState(research_id='fixture'))
    (folder/'case-info.json').write_text(json.dumps(dict(title='Fixture',synthetic_example=True)))
    prepare(store)
    request(workspace,cid,'agenda',dict(report_id='R1',items=[item()],rationale='Plan only'))
    view=Workspace(workspace.path).view(cid)
    assert view['reports'][0]['current'] and view['agendas'][0]['execution_authorized'] is False
    assert view['agendas'][0]['items'][0]['question']==item()['question']

def test_parallel_stale_writes_only_one_commits(workspace):
    cid=create(workspace)
    def attempt(i):
        try:return request(workspace,cid,'source',source(),expected_revision=1,expected_ledger_revision=0,request_id='parallel-'+str(i))
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert sum(r is not None for r in results)==1
    assert workspace.view(cid)['revision']==2 and workspace.view(cid)['ledger_revision']==1

class FakeServer:
    origin='http://127.0.0.1:12345'
    token='private-token'

@pytest.mark.parametrize('headers,api,write',[
    ({'Host':'evil.test'},False,False),
    ({'Host':'127.0.0.1:12345'},True,False),
    ({'Host':'127.0.0.1:12345','Authorization':'Bearer wrong'},True,False),
    ({'Host':'127.0.0.1:12345','Authorization':'Bearer private-token','Origin':'https://evil.test'},True,True),
    ({'Host':'127.0.0.1:12345','Authorization':'Bearer private-token'},True,True),
])
def test_http_guard_rejects_foreign_or_unauthenticated_requests(headers,api,write):
    handler=object.__new__(Handler);handler.server=FakeServer();handler.headers=headers
    with pytest.raises(PermissionError):handler._guard(api,write)

def test_http_guard_accepts_exact_local_origin_and_launch_token():
    handler=object.__new__(Handler);handler.server=FakeServer();handler.headers=dict(Host='127.0.0.1:12345',Origin=FakeServer.origin,Authorization='Bearer private-token')
    handler._guard(True,True)

@pytest.mark.parametrize('action',['publish','accept','execute','retrieve'])
def test_interface_does_not_expose_external_execution_or_acceptance(workspace,action):
    cid=create(workspace);before=workspace.view(cid)
    with pytest.raises(ValueError,match='unknown'):request(workspace,cid,action,dict(rationale='Unrecognized action'))
    assert workspace.view(cid)==before

@pytest.mark.parametrize('path,status',[('/',200),('/app.js',200),('/style.css',200),('/../local_app.py',404),('/research.sqlite',404),('/api/cases',200),('/api/state?case=../x',400)])
def test_http_get_routes_do_not_serve_private_files(workspace,path,status):
    handler=object.__new__(Handler);server=FakeServer();server.workspace=workspace
    handler.server=server;handler.headers=dict(Host='127.0.0.1:12345',Authorization='Bearer private-token');handler.path=path
    responses=[];handler._reply=lambda *args:responses.append(args)
    handler.do_GET();assert responses[0][0]==status

@pytest.mark.parametrize('headers,body',[
    ({'Content-Type':'text/plain','Content-Length':'2'},b'{}'),
    ({'Content-Type':'application/json','Content-Length':'2097153'},b''),
    ({'Content-Type':'application/json','Content-Length':'2','Transfer-Encoding':'chunked'},b'{}'),
    ({'Content-Type':'application/json','Content-Length':'1'},b'{'),
])
def test_http_rejects_invalid_payload_before_mutation(workspace,headers,body):
    import io,threading
    handler=object.__new__(Handler);server=FakeServer();server.workspace=workspace;server.mutation_lock=threading.Lock()
    handler.server=server;handler.headers=dict(Host='127.0.0.1:12345',Origin=server.origin,Authorization='Bearer private-token',**headers)
    handler.path='/api/cases';handler.rfile=io.BytesIO(body);responses=[];handler._reply=lambda *args:responses.append(args)
    handler.do_POST();assert responses[0][0]==400 and workspace.cases()==[]

def test_reframing_proposal_survives_restart_and_requires_exact_gate(workspace):
    cid=uuid.uuid4().hex;folder=workspace.path/cid;folder.mkdir()
    from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
    from dd_research_runtime.runtime import ResearchState
    from test_double_diamond import record_for
    store=PersistentEvidenceStore(folder/'research.sqlite');store.initialize(ResearchState(research_id='Fixture'))
    (folder/'case-info.json').write_text(json.dumps(dict(title='Fixture',synthetic_example=True)))
    prepare(store)
    request(workspace,cid,'propose_transition',dict(target='define',rationale='Reconsider the success criteria'),request_id='reopen')
    request(workspace,cid,'decide_gate',dict(gate_id='gate-reopen',decision='approve',rationale='Simulated review'))
    request(workspace,cid,'apply_gate',dict(gate_id='gate-reopen',rationale='Explicit simulated application'))
    changed=record_for('define');changed['success_criteria']=['A revised success criterion']
    result=request(workspace,cid,'phase_record',dict(record=changed,rationale='The criterion needs refinement'),request_id='frame')
    assert 'proposed' in result['notice']
    workspace=Workspace(workspace.path)
    assert 'define' not in workspace.view(cid)['state']['workflow']['records']
    request(workspace,cid,'decide_gate',dict(gate_id='gate-frame',decision='approve',rationale='Simulated exact frame review'))
    request(workspace,cid,'apply_gate',dict(gate_id='gate-frame',rationale='Explicit simulated frame application'))
    assert workspace.view(cid)['state']['workflow']['records']['define']==changed
