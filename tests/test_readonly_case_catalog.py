"""Case discovery must never adopt, initialize or repair saved research."""
import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from dd_research_runtime.local_app import Workspace
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.runtime import ResearchState
from test_local_app import create
from test_frame_revision import http_get


def candidate(w,*,database=b'',metadata=None):
    cid=uuid.uuid4().hex;folder=w.path/cid;folder.mkdir()
    (folder/'research.sqlite').write_bytes(database)
    (folder/'case-info.json').write_text(json.dumps(dict(title='Synthetic unavailable fixture',synthetic_example=True) if metadata is None else metadata))
    return cid,folder


@pytest.mark.parametrize('database',[b'',b'partial SQLite file',b'SQLite format 3\x00'+b'\x00'*128])
def test_invalid_databases_never_change_and_do_not_block_healthy_cases(tmp_path,database):
    w=Workspace(tmp_path/'workspace');healthy=create(w);cid,folder=candidate(w,database=database)
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    catalog=w.catalog()
    assert [c['case_id'] for c in catalog['cases']]==[healthy]
    assert catalog['unavailable_cases']==[dict(case_id=cid,title='Synthetic unavailable fixture',reason='case_unavailable')]
    assert {p.name:p.read_bytes() for p in folder.iterdir()}==before
    assert w.cases()==catalog['cases']


@pytest.mark.parametrize('metadata',[[],None,{'title':'Fixture','synthetic_example':'true'},{'title':4,'synthetic_example':True}])
def test_invalid_metadata_is_isolated_without_writing(tmp_path,metadata):
    w=Workspace(tmp_path/'workspace');healthy=create(w);cid,folder=candidate(w)
    (folder/'case-info.json').write_text(json.dumps(metadata));before=(folder/'case-info.json').read_bytes()
    catalog=w.catalog();assert [c['case_id'] for c in catalog['cases']]==[healthy]
    assert catalog['unavailable_cases'][0]['case_id']==cid
    assert (folder/'case-info.json').read_bytes()==before and (folder/'research.sqlite').read_bytes()==b''


def test_discovery_uses_no_mutating_store_constructor(tmp_path,monkeypatch):
    w=Workspace(tmp_path/'workspace');cid=create(w);path=w.case_path(cid)/'research.sqlite';before=path.read_bytes()
    def forbidden(*args,**kwargs):raise AssertionError('catalog invoked a mutating constructor')
    monkeypatch.setattr(PersistentEvidenceStore,'__init__',forbidden)
    assert w.catalog()['cases'][0]['case_id']==cid
    assert path.read_bytes()==before


def test_empty_reservations_and_private_staging_are_not_cases(tmp_path):
    w=Workspace(tmp_path/'workspace');(w.path/('a'*32)).mkdir();staged=w.path/'.example-incomplete';staged.mkdir();(staged/'research.sqlite').write_bytes(b'partial')
    assert w.catalog()==dict(cases=[],unavailable_cases=[])
    assert (staged/'research.sqlite').read_bytes()==b'partial'


@pytest.mark.parametrize('missing',['research.sqlite','case-info.json'])
def test_missing_case_component_is_reported_not_recreated(tmp_path,missing):
    w=Workspace(tmp_path/'workspace');cid,folder=candidate(w);(folder/missing).unlink()
    assert w.catalog()['unavailable_cases'][0]['case_id']==cid
    assert not (folder/missing).exists()


@pytest.mark.parametrize('name',['research.sqlite','case-info.json'])
def test_catalog_does_not_follow_case_file_symlinks(tmp_path,name):
    w=Workspace(tmp_path/'workspace');cid,folder=candidate(w);outside=tmp_path/'private fixture';outside.write_bytes(b'do not read or alter')
    (folder/name).unlink();(folder/name).symlink_to(outside)
    assert w.catalog()['unavailable_cases'][0]['case_id']==cid
    assert outside.read_bytes()==b'do not read or alter' and (folder/name).is_symlink()


def test_unsupported_workflow_is_reported_without_migration(tmp_path):
    w=Workspace(tmp_path/'workspace');cid,folder=candidate(w);(folder/'research.sqlite').unlink()
    PersistentEvidenceStore(folder/'research.sqlite').initialize(ResearchState(research_id='Synthetic legacy fixture'))
    before=(folder/'research.sqlite').read_bytes()
    assert w.catalog()['unavailable_cases'][0]['case_id']==cid
    assert (folder/'research.sqlite').read_bytes()==before


def test_http_catalog_is_authenticated_and_preserves_old_list_shape(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w);bad,_=candidate(w)
    assert http_get(w,'/api/catalog',False)[0]==403
    status,result=http_get(w,'/api/catalog');assert status==200
    assert result['cases'][0]['case_id']==cid and result['unavailable_cases'][0]['case_id']==bad
    status,legacy=http_get(w,'/api/cases');assert status==200 and legacy==result['cases']


def test_concurrent_creation_and_listing_only_expose_complete_cases(tmp_path):
    w=Workspace(tmp_path/'workspace')
    with ThreadPoolExecutor(max_workers=2) as pool:
        creating=pool.submit(lambda:[create(w) for _ in range(4)])
        for _ in range(8):
            catalog=w.catalog();assert not catalog['unavailable_cases']
            assert all(c['phase']=='discover' and c['revision']==1 for c in catalog['cases'])
        ids=creating.result()
    assert {c['case_id'] for c in w.catalog()['cases']}==set(ids)
