import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from zipfile import ZipFile,ZIP_DEFLATED

import pytest
from test_persistent_ingestion import store,ingest,auth
from test_pending_retrieval import queue,review_saved
from test_candidate_renewal import advance,renew,fresh_review
from test_candidate_termination import terminal_auth
from test_persistent_controller import prepare,output
from test_source_snapshots import snapshots
from dd_research_runtime import checkpoints
from dd_research_runtime.checkpoints import create_checkpoint,inspect_checkpoint,restore_checkpoint
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.pending_retrieval import PendingRetrievalQueue


def test_create_inspect_restore_preserves_state_gates_and_snapshots(store,tmp_path):
    ingest(store,source_snapshots=snapshots())
    before=store.load()[0].snapshot()
    archive=tmp_path/'checkpoint.zip'
    manifest=create_checkpoint(store,archive)
    assert inspect_checkpoint(archive) == manifest
    assert manifest['summary']['state_revision'] == 1
    restored=tmp_path/'restored.db'
    assert restore_checkpoint(archive,restored) == manifest
    copy=PersistentEvidenceStore(restored)
    assert copy.load()[0].snapshot() == before == store.load()[0].snapshot()
    assert copy.load_source_snapshots('s1') == snapshots()
    assert ingest(copy,source_snapshots=snapshots())['state_revision'] == 1
    assert copy.load()[0].human_gates['publication']['status'] == 'pending_review'


def test_all_candidate_lifecycles_preserved(queue,tmp_path):
    advance(queue);renew(queue)
    queue.commit('renewed',fresh_review(queue),authorize=auth,source_snapshots=snapshots())
    queue.save('cancelled',prepare(queue.store,executor=lambda **kw:output('s2')))
    queue.cancel('cancelled',actor='human',rationale='Withdrawn',authorize=terminal_auth)
    queue.save('rejected',prepare(queue.store,executor=lambda **kw:output('s3')))
    queue.reject('rejected',review_saved(queue.load('rejected'),decision='rejected'),expected_ledger_revision=2,authorize=terminal_auth)
    queue.save('pending',prepare(queue.store,executor=lambda **kw:output('s4')))
    archive=tmp_path/'full.zip';manifest=create_checkpoint(queue.store,archive)
    assert manifest['summary']['candidate_statuses'] == dict(superseded=1,committed=1,cancelled=1,rejected=1,pending=1)
    path=tmp_path/'full.db';restore_checkpoint(archive,path)
    q=PendingRetrievalQueue(PersistentEvidenceStore(path))
    assert q.load('candidate').successor_id == 'renewed'
    assert q.load('renewed').status == 'committed'
    assert q.load('cancelled').status == 'cancelled' and q.load('rejected').status == 'rejected'
    assert [c.candidate_id for c in q.list_pending()] == ['pending']
    assert q.store.load_source_snapshots('pending/renewed') == snapshots()


def test_wal_writer_during_backup_does_not_mix_revisions(store,tmp_path):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute('PRAGMA journal_mode=WAL')
    wrote=[]
    def concurrent_write(phase):
        if phase == 'during_backup' and not wrote:
            wrote.append(True)
            ingest(PersistentEvidenceStore(store.ledger.path),'s2',expected_state_revision=1,expected_ledger_revision=1)
    archive=tmp_path/'concurrent.zip'
    manifest=create_checkpoint(store,archive,_fault=concurrent_write)
    assert wrote and store.load()[1] == 2
    assert manifest['summary']['state_revision'] == manifest['summary']['ledger_revision'] == 1
    restored=tmp_path/'concurrent.db';restore_checkpoint(archive,restored)
    assert set(PersistentEvidenceStore(restored).load()[0].evidence) == {'s1'}


@pytest.mark.parametrize('action',['create','restore'])
def test_existing_destination_never_overwritten(store,tmp_path,action):
    archive=tmp_path/'source.zip';create_checkpoint(store,archive)
    destination=tmp_path/'existing';destination.write_bytes(b'preserve me')
    with pytest.raises(FileExistsError):
        if action == 'create':create_checkpoint(store,destination)
        else:restore_checkpoint(archive,destination)
    assert destination.read_bytes() == b'preserve me'


@pytest.mark.parametrize('action',['create','restore'])
@pytest.mark.parametrize('phase',['before_publish','after_publish'])
def test_publication_fault_is_absent_or_complete(store,tmp_path,action,phase):
    archive=tmp_path/'source.zip';create_checkpoint(store,archive)
    destination=tmp_path/'destination'
    def fail(name):
        if name == phase:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):
        if action == 'create':create_checkpoint(store,destination,_fault=fail)
        else:restore_checkpoint(archive,destination,_fault=fail)
    assert destination.exists() == (phase == 'after_publish')
    if destination.exists():
        if action == 'create':inspect_checkpoint(destination)
        else:assert PersistentEvidenceStore(destination).load()[1] == 0


def crash_create(path,destination,phase):
    def crash(name):
        if name == phase:os._exit(86)
    create_checkpoint(PersistentEvidenceStore(path),destination,_fault=crash)


@pytest.mark.parametrize('phase',['before_publish','after_publish'])
def test_process_death_at_publication(store,tmp_path,phase):
    destination=tmp_path/'crash.zip'
    p=multiprocessing.get_context('spawn').Process(target=crash_create,args=(store.ledger.path,destination,phase))
    p.start();p.join(15)
    if p.is_alive():p.terminate();p.join();pytest.fail('crash timeout')
    assert p.exitcode == 86
    assert destination.exists() == (phase == 'after_publish')
    if destination.exists():inspect_checkpoint(destination)


def rewrite_archive(source,target,mutate):
    with ZipFile(source) as archive:members={name:archive.read(name) for name in archive.namelist()}
    mutate(members)
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for name,data in members.items():archive.writestr(name,data)


@pytest.mark.parametrize('damage',['hash','summary','version','traversal','missing','database'])
def test_invalid_checkpoint_not_restored(store,tmp_path,damage):
    ingest(store)
    good=tmp_path/'good.zip';create_checkpoint(store,good)
    def mutate(members):
        manifest=json.loads(members['manifest.json'])
        if damage == 'hash':manifest['database_sha256']='wrong'
        elif damage == 'summary':manifest['summary']['state_revision']=999
        elif damage == 'version':manifest['version']=True
        elif damage == 'traversal':members['../escape']=b'bad'
        elif damage == 'missing':del members['research.sqlite']
        else:
            members['research.sqlite']=b'not a database'
            manifest['database_sha256']=sha256(members['research.sqlite']).hexdigest()
        members['manifest.json']=json.dumps(manifest)
    bad=tmp_path/'bad.zip';rewrite_archive(good,bad,mutate)
    destination=tmp_path/'restore.db'
    with pytest.raises(ValueError):restore_checkpoint(bad,destination)
    assert not destination.exists() and not (tmp_path/'escape').exists()


def test_recomputed_file_hash_cannot_hide_ledger_corruption(store,tmp_path):
    ingest(store)
    good=tmp_path/'good.zip';create_checkpoint(store,good)
    def mutate(members):
        dbpath=tmp_path/'edited.db';dbpath.write_bytes(members['research.sqlite'])
        with sqlite3.connect(dbpath) as db:db.execute("UPDATE receipts SET rationale='changed'")
        members['research.sqlite']=dbpath.read_bytes()
        manifest=json.loads(members['manifest.json'])
        manifest['database_sha256']=sha256(members['research.sqlite']).hexdigest()
        members['manifest.json']=json.dumps(manifest)
    bad=tmp_path/'bad.zip';rewrite_archive(good,bad,mutate)
    with pytest.raises(ValueError,match='integrity'):inspect_checkpoint(bad)


def test_source_corruption_not_repaired_or_published(store,tmp_path):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute('DELETE FROM ingestion_review_archive')
    destination=tmp_path/'corrupt.zip'
    with pytest.raises(ValueError,match='integrity'):create_checkpoint(store,destination)
    assert not destination.exists()
    with sqlite3.connect(store.ledger.path) as db:
        assert db.execute('SELECT COUNT(*) FROM ingestion_review_archive').fetchone()[0] == 0


def test_unknown_schema_not_silently_dropped(store,tmp_path):
    with sqlite3.connect(store.ledger.path) as db:db.execute('CREATE TABLE unrelated (value TEXT)')
    with pytest.raises(ValueError,match='schema'):create_checkpoint(store,tmp_path/'unsupported.zip')


def test_restore_size_limit_enforced_before_publication(store,tmp_path,monkeypatch):
    source=tmp_path/'source.zip';create_checkpoint(store,source)
    monkeypatch.setattr(checkpoints,'MAX_DATABASE_BYTES',1)
    destination=tmp_path/'too-big.db'
    with pytest.raises(ValueError,match='oversized'):restore_checkpoint(source,destination)
    assert not destination.exists()


def test_create_size_limit_leaves_no_output(store,tmp_path,monkeypatch):
    monkeypatch.setattr(checkpoints,'MAX_DATABASE_BYTES',1)
    destination=tmp_path/'too-big.zip'
    with pytest.raises(ValueError,match='byte limit'):create_checkpoint(store,destination)
    assert not destination.exists()


def test_concurrent_publication_has_one_winner(store,tmp_path):
    destination=tmp_path/'winner.zip'
    def run(_):
        try:create_checkpoint(store,destination);return 'created'
        except FileExistsError:return 'exists'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sorted(results) == ['created','exists']
    inspect_checkpoint(destination)


def test_duplicate_member_names_rejected(store,tmp_path):
    import warnings
    good=tmp_path/'good.zip';create_checkpoint(store,good)
    duplicate=tmp_path/'duplicate.zip'
    with ZipFile(good) as source, ZipFile(duplicate,'w') as target:
        for name in source.namelist():target.writestr(name,source.read(name))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            target.writestr('manifest.json',source.read('manifest.json'))
    with pytest.raises(ValueError,match='exactly two'):inspect_checkpoint(duplicate)


def test_duplicate_manifest_keys_rejected(store,tmp_path):
    good=tmp_path/'good.zip';create_checkpoint(store,good)
    def mutate(members):
        text=members['manifest.json'].decode()
        members['manifest.json']='{"version":1,'+text[1:]
    bad=tmp_path/'duplicate-key.zip';rewrite_archive(good,bad,mutate)
    with pytest.raises(ValueError,match='duplicate'):inspect_checkpoint(bad)


def test_summary_types_must_match_verified_content(store,tmp_path):
    ingest(store)
    good=tmp_path/'good.zip';create_checkpoint(store,good)
    def mutate(members):
        manifest=json.loads(members['manifest.json'])
        manifest['summary']['state_revision']=True
        members['manifest.json']=json.dumps(manifest)
    bad=tmp_path/'wrong-type.zip';rewrite_archive(good,bad,mutate)
    with pytest.raises(ValueError,match='summary integrity'):inspect_checkpoint(bad)


def test_incomplete_queue_schema_is_not_migrated(queue,tmp_path):
    with sqlite3.connect(queue.store.ledger.path) as db:db.execute('DROP TABLE candidate_renewals')
    destination=tmp_path/'incomplete.zip'
    with pytest.raises(ValueError,match='schema'):create_checkpoint(queue.store,destination)
    assert not destination.exists()
    with sqlite3.connect(queue.store.ledger.path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='candidate_renewals'").fetchone()


def test_legacy_review_coverage_preserved(tmp_path):
    from pathlib import Path
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript((Path(__file__).parent/'fixtures'/'cycle115_ingested.sql').read_text())
    source=PersistentEvidenceStore(path)
    archive=tmp_path/'legacy.zip';create_checkpoint(source,archive)
    restored=tmp_path/'restored.db';restore_checkpoint(archive,restored)
    assert PersistentEvidenceStore(restored).review_coverage() == source.review_coverage()
    with pytest.raises(LookupError,match='legacy'):PersistentEvidenceStore(restored).load_review('s1')


def test_published_files_are_owner_only(store,tmp_path):
    import stat
    archive=tmp_path/'private.zip';create_checkpoint(store,archive)
    database=tmp_path/'private.db';restore_checkpoint(archive,database)
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
