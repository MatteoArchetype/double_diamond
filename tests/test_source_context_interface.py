"""Retained context inspection is read-only; invented evidence only."""
import json
import sqlite3
import pytest
from dd_research_runtime.local_app import Workspace
from dd_research_runtime.source_review import read_source
from test_local_app import create,request,source
from test_frame_revision import http_get
from test_persistent_ingestion import store,ingest
from test_source_snapshots import snapshots


@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w)
    for name in ('first','second'):
        request(w,cid,'source',source(title='Synthetic '+name,url='https://example.org/'+name,passage='Invented '+name+'.',snapshot='Before. Invented '+name+'. After.'),request_id=name)
    return w,cid


def test_original_snapshot_and_review_are_read_only_and_isolated(case):
    w,cid=case;before=w.view(cid);path=w.case_path(cid)/'research.sqlite';raw=path.read_bytes()
    result=w.source_context(cid,'synthetic-first',before['revision'])
    assert result['context_status']=='retained_snapshot'
    assert result['snapshot']==dict(text='Before. Invented first. After.',location='section 1')
    assert result['evidence']==before['state']['evidence']['synthetic-first']
    assert result['review']['decision']=='approved' and result['evidence']['synthetic'] is True
    assert 'Invented second.' not in json.dumps(result)
    result['snapshot']['text']='Detached mutation';result['review']['decision']='invented'
    assert w.source_context(cid,'synthetic-first',before['revision'])['snapshot']['text']=='Before. Invented first. After.'
    assert w.view(cid)==before and path.read_bytes()==raw


@pytest.mark.parametrize('revision',[None,True,-1,'1',1.5])
def test_revision_must_be_explicit_integer(case,revision):
    w,cid=case
    with pytest.raises(ValueError):w.source_context(cid,'synthetic-first',revision)


@pytest.mark.parametrize('eid',['missing','../first','',True,'x'*257])
def test_unknown_or_invalid_evidence_makes_no_write(case,eid):
    w,cid=case;before=w.view(cid)
    with pytest.raises(ValueError):w.source_context(cid,eid,before['revision'])
    assert w.view(cid)==before


def test_stale_revision_refused_without_substituting_current_context(case):
    w,cid=case;revision=w.view(cid)['revision']
    request(w,cid,'claim',dict(claim='Synthetic interpretation',claim_type='descriptive',evidence_ids=['synthetic-first'],rationale='Fixture'))
    before=w.view(cid)
    with pytest.raises(RuntimeError,match='changed'):w.source_context(cid,'synthetic-first',revision)
    assert w.view(cid)==before


def test_checkpoint_recovery_retains_same_intake_context(case):
    w,cid=case;before=w.view(cid);context=w.source_context(cid,'synthetic-first',before['revision'])
    data,_=w.backup(cid,before['revision']);preview=w.inspect_backup(data);restored=w.restore_backup(data,preview['checkpoint_digest'])
    assert restored['approval_granted'] is False
    assert Workspace(w.path).source_context(restored['case_id'],'synthetic-first',before['revision'])==context


def test_review_without_snapshot_never_invents_surrounding_text(store):
    ingest(store);state,revision=store.load();result=read_source(store.ledger.path,'s1',expected_revision=revision)
    assert result['context_status']=='review_only' and result['snapshot'] is None and result['review']['decision']=='approved'


def test_adopted_historical_evidence_never_gets_a_fabricated_review(case,tmp_path):
    from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
    w,cid=case;path=tmp_path/'adopted.sqlite';adopted=PersistentEvidenceStore(path);adopted.initialize(w.store(cid).load()[0])
    result=read_source(path,'synthetic-first',expected_revision=0)
    assert result['context_status']=='unavailable' and result['review'] is None and result['snapshot'] is None and result['operation_id'] is None


def test_tampered_archive_is_refused_not_displayed(case):
    w,cid=case;path=w.case_path(cid)/'research.sqlite';revision=w.view(cid)['revision']
    with sqlite3.connect(path) as db:db.execute("UPDATE ingestion_review_archive SET payload='{}' WHERE operation_id='ui-first'")
    with pytest.raises(ValueError):read_source(path,'synthetic-first',expected_revision=revision)


def test_http_context_requires_private_launch_token_and_exact_revision(case):
    w,cid=case;revision=w.view(cid)['revision'];path='/api/source-context?case='+cid+'&evidence=synthetic-first&revision='+str(revision)
    assert http_get(w,path,False)[0]==403
    status,result=http_get(w,path);assert status==200 and result['context_status']=='retained_snapshot'
    assert http_get(w,path.replace('revision='+str(revision),'revision=0'))[0]==409
    assert http_get(w,path.split('&revision=')[0])[0]==400
    assert http_get(w,path.replace('revision='+str(revision),'revision=true'))[0]==400


def test_context_stays_pinned_during_concurrent_saved_change(case):
    w,cid=case;path=w.case_path(cid)/'research.sqlite'
    # WAL allows the writer to commit while the inspection keeps its original read snapshot.
    with sqlite3.connect(path) as db:assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
    revision=w.view(cid)['revision']
    def concurrent_write():
        request(w,cid,'uncertainty',dict(question='Synthetic concurrent gap?',claim_ids=[],rationale='Fixture'))
    result=read_source(path,'synthetic-first',expected_revision=revision,_after_pin=concurrent_write)
    assert result['state_revision']==revision and result['snapshot']['text']=='Before. Invented first. After.'
    assert w.view(cid)['revision']==revision+1
    with pytest.raises(RuntimeError):w.source_context(cid,'synthetic-first',revision)
