"""Opening state and downloading saved reports cannot initialize or migrate files."""
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from dd_research_runtime.local_app import Workspace,ACTOR,_authorize
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.reporting import render_markdown
from test_local_app import create
from test_frame_revision import http_get


@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w);return w,cid


@pytest.mark.parametrize('database',[b'',b'partial fixture database'])
@pytest.mark.parametrize('kind',['state','report'])
def test_direct_reads_leave_incomplete_database_unchanged(tmp_path,database,kind):
    w=Workspace(tmp_path/'workspace');cid=uuid.uuid4().hex;folder=w.path/cid;folder.mkdir();path=folder/'research.sqlite';path.write_bytes(database)
    (folder/'case-info.json').write_text(json.dumps(dict(title='Synthetic interrupted fixture',synthetic_example=True)))
    with pytest.raises((ValueError,RuntimeError,sqlite3.Error)):
        if kind=='state':w.view(cid)
        else:w.report(cid,'missing')
    assert path.read_bytes()==database
    assert {p.name for p in folder.iterdir()}=={'case-info.json','research.sqlite'}


@pytest.mark.parametrize('kind',['state','report'])
def test_browser_reads_use_no_mutating_constructor(case,kind,monkeypatch):
    w,cid=case;path=w.case_path(cid)/'research.sqlite';before=path.read_bytes()
    def forbidden(*args,**kwargs):raise AssertionError('read invoked mutating constructor')
    monkeypatch.setattr(PersistentEvidenceStore,'__init__',forbidden)
    if kind=='state':assert w.view(cid)['revision']==1
    else:
        with pytest.raises(ValueError,match='unknown report'):w.report(cid,'missing')
    assert path.read_bytes()==before


@pytest.mark.parametrize('metadata',[[],None,{'title':'Fixture','synthetic_example':'false'},{'title':True,'synthetic_example':False}])
def test_bad_metadata_is_refused_before_database_initialization(tmp_path,metadata):
    w=Workspace(tmp_path/'workspace');cid=uuid.uuid4().hex;folder=w.path/cid;folder.mkdir();path=folder/'research.sqlite';path.write_bytes(b'')
    (folder/'case-info.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError):w.view(cid)
    assert path.read_bytes()==b''


def test_state_open_does_not_follow_metadata_symlink(case,tmp_path):
    w,cid=case;folder=w.case_path(cid);outside=tmp_path/'private fixture';outside.write_text(json.dumps(dict(title='Private fixture',synthetic_example=False)))
    (folder/'case-info.json').unlink();(folder/'case-info.json').symlink_to(outside)
    before=(folder/'research.sqlite').read_bytes()
    with pytest.raises(ValueError,match='metadata link'):w.view(cid)
    assert (folder/'research.sqlite').read_bytes()==before and outside.exists()


def test_http_state_and_saved_report_still_require_private_access(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=w.demo();before=w.view(cid);rid=before['reports'][0]['report_id']
    state_path='/api/state?case='+cid;report_path='/api/report?case='+cid+'&report='+rid
    for path in (state_path,report_path):assert http_get(w,path,False)[0]==403
    assert http_get(w,state_path)[0]==200
    status,markdown,content_type=http_get(w,report_path)
    assert status==200 and markdown==render_markdown(before['state']['outputs'][rid]) and content_type.startswith('text/markdown')
    assert w.view(cid)==before


def test_checkpoint_recovery_preserves_state_and_saved_report_reads(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=w.demo();before=w.view(cid);rid=before['reports'][0]['report_id'];report=w.report(cid,rid)
    data,_=w.backup(cid,before['revision']);preview=w.inspect_backup(data);result=w.restore_backup(data,preview['checkpoint_digest']);restored=result['case_id']
    assert result['approval_granted'] is False
    assert w.view(restored)['state']==before['state'] and w.report(restored,rid)==report


def test_concurrent_open_returns_consistent_detached_state_and_revision(case):
    w,cid=case;store=w.store(cid)
    def write_questions():
        for i in range(4):
            store.apply_analysis([dict(type='put_uncertainty',record=dict(uncertainty_id='fixture-'+str(i),question='Invented gap '+str(i),status='open'))],operation_id='question-'+str(i),actor=ACTOR,rationale='Synthetic concurrency test',expected_state_revision=i+1,authorize=_authorize)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer=pool.submit(write_questions)
        for _ in range(8):
            view=w.view(cid);assert view['revision']==len(view['state']['uncertainties'])+1
            assert not view['state']['human_gates']
        writer.result()
    assert w.view(cid)['revision']==5


def test_read_only_state_is_detached_from_future_inspection(case):
    w,cid=case;view=w.view(cid);view['state']['brief']['text']='Changed only in caller copy'
    assert w.view(cid)['state']['brief']['text']!='Changed only in caller copy'


def test_prejournal_case_open_does_not_adopt_or_migrate(case):
    w,cid=case;state=w.store(cid).load()[0];other=uuid.uuid4().hex;folder=w.path/other;folder.mkdir();path=folder/'research.sqlite'
    PersistentEvidenceStore(path).initialize(state)
    (folder/'case-info.json').write_text(json.dumps(dict(title='Synthetic prejournal fixture',synthetic_example=True)))
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE state_mutations');db.execute('DROP TABLE state_journal_policy')
    before=path.read_bytes();view=w.view(other)
    assert view['revision']==0 and view['state']['workflow']['phase']=='discover' and path.read_bytes()==before
    with sqlite3.connect(path) as db:assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'state_journal%' OR name='state_mutations'").fetchall()
