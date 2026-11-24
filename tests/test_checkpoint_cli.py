import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from test_persistent_ingestion import store,ingest
from test_source_snapshots import snapshots
from dd_research_runtime import checkpoint_cli
from dd_research_runtime.checkpoints import create_checkpoint,verify_database,create_checkpoint_from_path,_ReadOnlySource
from dd_research_runtime.local_app import Workspace
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore

ROOT=Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run([sys.executable,'-m','dd_research_runtime.checkpoint_cli',*map(str,args)],
                          cwd=ROOT,text=True,capture_output=True,timeout=20)


def success(result):
    assert result.returncode == 0 and result.stderr == ''
    data=json.loads(result.stdout)
    assert data['ok'] is True
    return data


def failure(result,code,status=1):
    assert result.returncode == status and result.stdout == ''
    data=json.loads(result.stderr)
    assert data['ok'] is False and data['error']['code'] == code
    assert 'Traceback' not in result.stderr
    return data


def test_real_cli_create_inspect_restore_verify(store,tmp_path):
    ingest(store,source_snapshots=snapshots())
    original=Path(store.ledger.path).read_bytes()
    archive=tmp_path/'research backup.zip'
    created=success(run_cli('create',store.ledger.path,archive))
    assert Path(store.ledger.path).read_bytes() == original
    inspected=success(run_cli('inspect',archive,'--pretty'))
    assert inspected['manifest'] == created['manifest']
    restored=tmp_path/'restored research.db'
    assert success(run_cli('restore',archive,restored))['manifest'] == created['manifest']
    report=success(run_cli('verify',restored))
    assert report['summary']['state_revision'] == 1
    assert PersistentEvidenceStore(restored).load_source_snapshots('s1') == snapshots()
    assert 'Exact passage s1' not in json.dumps(inspected)
    assert 'Checked independent snapshot' not in json.dumps(inspected)


@pytest.mark.parametrize('command',['create','verify'])
def test_missing_database_not_created(tmp_path,command):
    missing=tmp_path/'missing.db'
    args=[command,missing]
    if command == 'create':args.append(tmp_path/'backup.zip')
    failure(run_cli(*args),'not_found')
    assert not missing.exists() and not (tmp_path/'backup.zip').exists()


@pytest.mark.parametrize('command',['create','restore'])
def test_existing_destination_no_force_replacement(store,tmp_path,command):
    archive=tmp_path/'source.zip';create_checkpoint(store,archive)
    existing=tmp_path/'existing';existing.write_bytes(b'preserve me')
    args=[command,store.ledger.path if command == 'create' else archive,existing]
    failure(run_cli(*args),'destination_exists')
    assert existing.read_bytes() == b'preserve me'


def test_cli_validation_error_contains_no_traceback(store,tmp_path):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute('DELETE FROM ingestion_review_archive')
    failure(run_cli('verify',store.ledger.path),'invalid_data')
    output=tmp_path/'blocked.zip'
    failure(run_cli('create',store.ledger.path,output),'invalid_data')
    assert not output.exists()


def test_pre_adoption_database_not_silently_migrated(tmp_path):
    path=tmp_path/'legacy.db'
    fixture=ROOT/'tests'/'fixtures'/'cycle115_ingested.sql'
    with sqlite3.connect(path) as db:db.executescript(fixture.read_text())
    before=path.read_bytes()
    failure(run_cli('verify',path),'invalid_data')
    failure(run_cli('create',path,tmp_path/'legacy.zip'),'invalid_data')
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='review_archive_policy'").fetchone()


@pytest.mark.parametrize('args',[[],['unknown'],['create'],['restore'],['verify'],['inspect'],['verify','missing','--force']])
def test_usage_errors_have_stable_exit_and_json(args):
    failure(run_cli(*args),'usage',status=2)


@pytest.mark.parametrize('args',[['--help'],['create','--help'],['inspect','--help'],['restore','--help'],['restore-case','--help'],['verify','--help']])
def test_help_requires_no_database(args):
    result=run_cli(*args)
    assert result.returncode == 0 and result.stderr == '' and 'usage:' in result.stdout


def test_corrupt_checkpoint_inspection_and_restore(tmp_path):
    bad=tmp_path/'broken.zip';bad.write_bytes(b'not a zip')
    failure(run_cli('inspect',bad),'invalid_data')
    destination=tmp_path/'restore.db'
    failure(run_cli('restore',bad,destination),'invalid_data')
    assert not destination.exists()


def test_verify_does_not_repair_incomplete_queue(store,tmp_path):
    from dd_research_runtime.pending_retrieval import PendingRetrievalQueue
    PendingRetrievalQueue(store)
    with sqlite3.connect(store.ledger.path) as db:db.execute('DROP TABLE candidate_renewals')
    failure(run_cli('verify',store.ledger.path),'invalid_data')
    with sqlite3.connect(store.ledger.path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='candidate_renewals'").fetchone()


def test_readonly_connection_rejects_write(store):
    connection=_ReadOnlySource(store.ledger.path)._connect()
    try:
        with pytest.raises(sqlite3.OperationalError):connection.execute('CREATE TABLE accidental_write (value TEXT)')
    finally:connection.close()
    assert verify_database(store.ledger.path)['state_revision'] == 0


def test_uri_special_characters_and_spaces(store,tmp_path):
    # '?' cannot appear in a Windows file name, so only other platforms exercise it.
    suffix='? # %.db' if os.name!='nt' else '# %.db'
    source=tmp_path/('source '+suffix)
    # Closed rollback-journal source has no pending WAL; copy is fixture setup only.
    source.write_bytes(Path(store.ledger.path).read_bytes())
    archive=tmp_path/('backup '+suffix.replace('.db','.zip'))
    success(run_cli('create',source,archive))
    success(run_cli('inspect',archive))


def test_permission_error_category(monkeypatch,capsys):
    def denied(path):raise PermissionError('Access denied')
    monkeypatch.setattr(checkpoint_cli,'verify_database',denied)
    assert checkpoint_cli.main(['verify','source.db']) == 1
    output=capsys.readouterr()
    assert output.out == '' and json.loads(output.err)['error']['code'] == 'permission_denied'


def test_interrupt_does_not_report_success(monkeypatch,capsys):
    def interrupt(path):raise KeyboardInterrupt()
    monkeypatch.setattr(checkpoint_cli,'verify_database',interrupt)
    assert checkpoint_cli.main(['verify','source.db']) == 130
    output=capsys.readouterr()
    assert output.out == ''
    data=json.loads(output.err)
    assert data['error']['code'] == 'interrupted' and 'Inspect' in data['error']['message']


def test_library_path_creation_uses_readonly_source(store,tmp_path):
    original=Path(store.ledger.path).read_bytes()
    manifest=create_checkpoint_from_path(store.ledger.path,tmp_path/'library.zip')
    assert manifest['summary'] == verify_database(store.ledger.path)
    assert Path(store.ledger.path).read_bytes() == original


def test_restore_case_cli_publishes_separate_browser_case(tmp_path):
    workspace=Workspace(tmp_path/'workspace')
    original=workspace.create(dict(title='Original case',question='What remains unknown?',
                                   scope='Test only',max_visits=8,max_alternatives=3))
    original_database=workspace.path/original/'research.sqlite'
    original_bytes=original_database.read_bytes()
    archive=tmp_path/'research.zip'
    success(run_cli('create',original_database,archive))

    restored=success(run_cli('restore-case',archive,workspace.path))
    assert restored['restored_checkpoint'] is True
    assert restored['approval_granted'] is False
    assert restored['case_id'] != original
    assert original_database.read_bytes() == original_bytes
    assert {item['case_id'] for item in workspace.cases()} == {original,restored['case_id']}
    restored_view=workspace.view(restored['case_id'])
    assert restored_view['meta']['restored_checkpoint'] is True
    assert restored_view['state']['workflow']['workflow_version'] == 3
