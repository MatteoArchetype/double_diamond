"""Visit inspection never changes research or manufactures historical evidence."""
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from test_persistent_ingestion import store
from test_decision_trace import setup,save
from test_double_diamond import move,record_for,approve
from test_analysis_transactions import apply
from test_workflow import write
from dd_research_runtime.visit_review import read_visit
from dd_research_runtime.double_diamond import reframing_action
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.runtime import ResearchState
from dd_research_runtime.local_app import Workspace,Handler


def test_each_phase_has_complete_original_context_and_no_side_effects(store):
    setup(store);save(store);before=store.load()[0].snapshot();revision=store.load()[1]
    for index,phase in enumerate(['discover','define','develop','deliver'],1):
        result=read_visit(store.ledger.path,'V'+str(index),expected_revision=revision)
        assert result['visit']['phase']==phase and result['context_status']=='verified_original'
        assert result['current_binding_matches'] and result['recorded_revision']<=revision
        assert result['recording_actor']=='fixture-human'
        assert result['context']['evidence']['s1']['finding']=='Exact passage s1'
        assert result['context']['evidence']['s1']['synthetic'] is False
        assert result['context']['sources']['s1']['url']=='https://example.org/s1'
        assert result['context']['brief']==before['brief'] and result['context']['scope']==before['scope']
        if phase=='deliver':
            assert result['context']['defined_problem']['success_criteria']==['Bound the explanation','State remaining uncertainty']
            assert len(result['visit']['record']['criterion_assessments'])==2
            assert len(result['context']['developed_alternatives']['alternatives'])==2
    assert store.load()[0].snapshot()==before and store.ledger.revision()==1


def test_later_claim_edit_does_not_replace_original_interpretation(store):
    setup(store);save(store);original=read_visit(store.ledger.path,'V2')
    revision=store.load()[1]
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(claim='Later revised explanation'))],operation_id='later-analysis',expected_state_revision=revision)
    result=read_visit(store.ledger.path,'V2')
    assert result['context']==original['context']
    assert result['context']['claims']['C1']['claim']=='Bounded fixture claim'
    assert result['is_current_record'] and not result['current_binding_matches']
    assert store.load()[0].claims['C1']['claim']=='Later revised explanation'


def test_returned_values_are_detached_from_database(store):
    setup(store);result=read_visit(store.ledger.path,'V2')
    result['visit']['record']['problem']='Corrupt local copy';result['context']['claims']['C1']['claim']='Detached edit'
    assert read_visit(store.ledger.path,'V2')['visit']['record']['problem']!='Corrupt local copy'
    assert read_visit(store.ledger.path,'V2')['context']['claims']['C1']['claim']!='Detached edit'


def test_previous_frame_comparison_and_identical_revisit_currency(store):
    setup(store);save(store);move(store,'define','revisit')
    original=read_visit(store.ledger.path,'V2');value=copy.deepcopy(original['visit']['record'])
    write(store,dict(type='record',phase='define',record=value))
    older=read_visit(store.ledger.path,'V2');newer=read_visit(store.ledger.path,'V5')
    assert not older['is_current_record'] and newer['is_current_record']
    assert newer['previous_visit_id']=='V2' and newer['changed_fields']==[]
    assert older['context']==original['context']


def test_reframed_visit_retains_before_and_after_records(store):
    setup(store);save(store);move(store,'define','revisit')
    original=read_visit(store.ledger.path,'V2');value=record_for('define');value['success_criteria']=['Revised criterion']
    approve(store,reframing_action(store.load()[0],value),'reframe')
    write(store,dict(type='record',phase='define',record=value,gate_id='reframe'))
    result=read_visit(store.ledger.path,'V5')
    assert result['previous_record']==original['visit']['record']
    assert result['changed_fields']==['success_criteria']
    assert result['visit']['record']['success_criteria']==['Revised criterion']
    assert read_visit(store.ledger.path,'V2')['context']==original['context']


def test_open_visit_does_not_invent_findings_or_context(store):
    setup(store);result=read_visit(store.ledger.path,'V4')
    assert result['context_status']=='not_recorded' and result['context'] is None
    assert result['recorded_revision'] is None and result['visit']['record'] is None
    assert not result['is_current_record'] and result['is_latest_visit']


@pytest.mark.parametrize('visit',['missing','../V2','',None,'a'*81])
def test_invalid_visit_refuses_without_writes(store,visit):
    setup(store);before=store.load()[0].snapshot()
    with pytest.raises(ValueError):read_visit(store.ledger.path,visit)
    assert store.load()[0].snapshot()==before


@pytest.mark.parametrize('revision',[True,-1,'2',1.5])
def test_invalid_expected_revision_refused(store,revision):
    setup(store)
    with pytest.raises(ValueError):read_visit(store.ledger.path,'V1',expected_revision=revision)


def test_stale_browser_revision_refused(store):
    setup(store)
    with pytest.raises(RuntimeError,match='changed'):read_visit(store.ledger.path,'V1',expected_revision=1)


def test_missing_database_is_not_created(tmp_path):
    path=tmp_path/'absent.sqlite'
    with pytest.raises(FileNotFoundError):read_visit(path,'V1')
    assert not path.exists()


def test_bootstrap_record_does_not_borrow_current_context(store,tmp_path):
    setup(store);save(store)
    boot=PersistentEvidenceStore(tmp_path/'bootstrap.sqlite');boot.initialize(store.load()[0])
    result=read_visit(boot.ledger.path,'V2')
    assert result['context_status']=='unavailable' and result['context'] is None
    assert result['visit']['record']['problem']=='A bounded interpretation problem'
    assert result['recording_actor'] is None and result['recorded_revision'] is None


def test_legacy_workflow_refused_without_migration(store):
    before=Path(store.ledger.path).read_bytes()
    with pytest.raises(ValueError,match='Double Diamond'):read_visit(store.ledger.path,'V1')
    assert Path(store.ledger.path).read_bytes()==before


@pytest.mark.parametrize('column',['after_snapshot','request','after_hash'])
def test_tampered_journal_context_is_refused(store,column):
    setup(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute('UPDATE state_mutations SET '+column+'=? WHERE revision=4',('tampered',))
    with pytest.raises(ValueError,match='integrity'):read_visit(store.ledger.path,'V1')


def test_review_uses_one_pinned_snapshot_during_concurrent_write(store):
    setup(store);save(store);revision=store.load()[1]
    with sqlite3.connect(store.ledger.path) as db:db.execute('PRAGMA journal_mode=WAL')
    def change():
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(apply,store,[dict(type='update_claim',claim_id='C1',patch=dict(claim='Concurrent revised interpretation'))],operation_id='concurrent',expected_state_revision=revision).result(timeout=10)
    result=read_visit(store.ledger.path,'V2',expected_revision=revision,_after_pin=change)
    assert result['state_revision']==revision and result['current_binding_matches']
    assert result['context']['claims']['C1']['claim']=='Bounded fixture claim'
    later=read_visit(store.ledger.path,'V2')
    assert later['state_revision']==revision+1 and not later['current_binding_matches']
    with pytest.raises(RuntimeError):read_visit(store.ledger.path,'V2',expected_revision=revision)


def test_read_only_snapshot_checkpoint_reopens_identically(store,tmp_path):
    setup(store);save(store);path=tmp_path/'checkpoint.zip';create_checkpoint(store,path)
    target=tmp_path/'restored.sqlite';restore_checkpoint(path,target)
    before=hashlib.sha256(target.read_bytes()).hexdigest();stat=target.stat()
    assert read_visit(target,'V3')==read_visit(store.ledger.path,'V3')
    assert hashlib.sha256(target.read_bytes()).hexdigest()==before and target.stat().st_mtime_ns==stat.st_mtime_ns


def test_workspace_and_authenticated_route_expose_inspection_only(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=w.demo();state=w.view(cid)
    handler=object.__new__(Handler)
    class Server:origin='http://127.0.0.1:12345';token='private';workspace=w
    handler.server=Server();handler.headers=dict(Host='127.0.0.1:12345',Authorization='Bearer private')
    handler.path='/api/visit?case='+cid+'&visit=V3&revision='+str(state['revision'])
    replies=[];handler._reply=lambda *args:replies.append(args);handler.do_GET()
    assert replies[0][0]==200 and replies[0][1]['visit']['phase']=='develop'
    assert any(e['synthetic'] for e in replies[0][1]['context']['evidence'].values())
    assert w.view(cid)==state
    handler.headers.pop('Authorization');replies.clear();handler.do_GET();assert replies[0][0]==403


@pytest.mark.parametrize('revision',['-1','true','1.5','%D9%A1',''])
def test_http_revision_validation(tmp_path,revision):
    w=Workspace(tmp_path/'workspace');cid=w.create(dict(title='Fixture',question='What remains unknown?',scope='Test only',max_visits=8,max_alternatives=3));handler=object.__new__(Handler)
    class Server:origin='http://127.0.0.1:12345';token='private';workspace=w
    handler.server=Server();handler.headers=dict(Host='127.0.0.1:12345',Authorization='Bearer private')
    handler.path='/api/visit?case='+cid+'&visit=V1&revision='+revision
    replies=[];handler._reply=lambda *args:replies.append(args);handler.do_GET()
    assert replies[0][0]==400


def test_genuine_cycle135_checkpoint_keeps_original_visit_context(tmp_path):
    fixture=Path(__file__).parent/'fixtures'/'cycle135-visit-review.zip'
    target=tmp_path/'cycle135.sqlite';restore_checkpoint(fixture,target)
    earlier=read_visit(target,'V2');later=read_visit(target,'V5')
    assert earlier['context_status']==later['context_status']=='verified_original'
    assert earlier['visit']['record']['problem']=='Explain the example'
    assert later['visit']['record']['problem']=='Identify what remains unknown about the example'
    assert later['previous_record']==earlier['visit']['record']
    assert later['changed_fields']==['problem']
    assert not earlier['is_current_record'] and later['is_current_record']
    assert all(e['synthetic'] for e in earlier['context']['evidence'].values())
    assert read_visit(target,'V7')['context']['defined_problem']==later['visit']['record']


def test_http_stale_review_is_conflict_not_silent_refresh(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=w.create(dict(title='Fixture',question='What remains unknown?',scope='Test only',max_visits=8,max_alternatives=3))
    handler=object.__new__(Handler)
    class Server:origin='http://127.0.0.1:12345';token='private';workspace=w
    handler.server=Server();handler.headers=dict(Host='127.0.0.1:12345',Authorization='Bearer private')
    handler.path='/api/visit?case='+cid+'&visit=V1&revision=0'
    replies=[];handler._reply=lambda *args:replies.append(args);handler.do_GET()
    assert replies[0][0]==409 and 'changed' in replies[0][1]['error']
    assert w.view(cid)['revision']==1
