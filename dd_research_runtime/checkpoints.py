"""Consistent SQLite checkpoints with verified, non-overwriting publication.

Checkpoints contain plaintext database content. Hashes detect partial corruption,
not authenticity or coordinated rewriting. External executor state is not included.
"""
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED, BadZipFile

from .persistent_ingestion import PersistentEvidenceStore, _encode
from .review_ledger import ReviewLedger
from .review_archive import verify_archive

MAX_DATABASE_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
BASE_TABLES = {'receipts','research_state','ingestion_operations','review_archive_policy','ingestion_review_archive'}
JOURNAL_TABLES = {'state_journal_policy','state_mutations'}
QUEUE_TABLES = {'pending_retrievals','retrieval_terminations','candidate_renewals'}


def _hash_file(path):
    digest=sha256()
    with open(path,'rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def _validate_database(path):
    # Bind read helpers without invoking constructors, migration or repair.
    store=object.__new__(PersistentEvidenceStore)
    store.ledger=object.__new__(ReviewLedger)
    store.ledger.path=str(path)
    with closing(sqlite3.connect(f'{Path(path).as_uri()}?mode=ro',uri=True,isolation_level=None)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('checkpoint SQLite integrity mismatch')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
            raise ValueError('unsupported checkpoint schema objects')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'")}
        if not tables >= BASE_TABLES or tables-BASE_TABLES-QUEUE_TABLES-JOURNAL_TABLES or (tables & QUEUE_TABLES and not tables >= QUEUE_TABLES) or (tables & JOURNAL_TABLES and not tables >= JOURNAL_TABLES):
            raise ValueError('unsupported or incomplete checkpoint schema')
        state,sr,lr,operations=store._verify_integrity(db)
        rows=db.execute('SELECT operation_id,request_digest,review_digest,result,result_digest FROM ingestion_operations').fetchall()
        coverage=verify_archive(db,rows)
        status_counts={}
        if tables >= QUEUE_TABLES:
            from .pending_retrieval import PendingRetrievalQueue
            queue=object.__new__(PendingRetrievalQueue);queue.store=store
            status_counts=dict(sorted(Counter(c.status for c in queue._verify(db)).items()))
        snapshot_sets=sum('source_snapshots' in json.loads(row[0]) for row in db.execute('SELECT payload FROM ingestion_review_archive'))
        summary=dict(state_revision=sr,ledger_revision=lr,operations=operations,
                     review_coverage=coverage,retained_snapshot_sets=snapshot_sets,
                     candidate_statuses=status_counts,tables=sorted(tables))
        if tables >= JOURNAL_TABLES:
            from .state_journal import verify
            summary['state_mutations']=verify(db,state,sr,rows)
        return summary


def _destination(path):
    path=Path(path).absolute()
    if path.exists() or path.is_symlink():raise FileExistsError('checkpoint destination already exists: '+str(path))
    if not path.parent.is_dir():raise FileNotFoundError('destination parent must exist')
    return path


def _publish(staged,destination,fault):
    os.chmod(staged,0o600)
    # Windows flushes only a handle opened for writing; a read-only handle raises EBADF.
    descriptor=os.open(staged,os.O_RDWR)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    if fault is not None:fault('before_publish')
    os.link(staged,destination) # Atomic exclusive publication; never replace an existing path.
    if fault is not None:fault('after_publish')


def create_checkpoint(store,destination,*,expected_state_revision=None,_fault=None):
    """Back up one consistent SQLite read snapshot, verify and publish a ZIP.

    Existing destinations are never overwritten. A post-publication exception may
    leave a complete artifact; inspect it rather than deleting or replacing it.
    """
    if expected_state_revision is not None and (type(expected_state_revision) is not int or expected_state_revision<0):raise ValueError('invalid expected state revision')
    destination=_destination(destination)
    with tempfile.TemporaryDirectory(prefix='.dd-checkpoint-',dir=destination.parent) as temp:
        root=Path(temp);database=root/'research.sqlite'
        with closing(store._connect()) as source, closing(sqlite3.connect(database)) as target:
            source.execute('PRAGMA query_only=ON')
            source.execute('BEGIN')
            pinned=source.execute('SELECT revision FROM research_state WHERE id=1').fetchone() # Pin snapshot.
            if expected_state_revision is not None and (not pinned or pinned[0]!=expected_state_revision):raise RuntimeError('This case changed. Refresh before creating the backup.')
            def progress(status,remaining,total):
                if total*source.execute('PRAGMA page_size').fetchone()[0] > MAX_DATABASE_BYTES:
                    raise ValueError('checkpoint database exceeds byte limit')
                if _fault is not None:_fault('during_backup')
            source.backup(target,pages=128,progress=progress)
            source.execute('ROLLBACK')
            target.execute('PRAGMA journal_mode=DELETE')
        if database.stat().st_size > MAX_DATABASE_BYTES:raise ValueError('checkpoint database exceeds byte limit')
        os.chmod(database,0o600)
        summary=_validate_database(database)
        manifest=dict(format='double-diamond-checkpoint',version=1,database_sha256=_hash_file(database),summary=summary)
        staged=root/'checkpoint.zip'
        encoded_manifest=_encode(manifest)
        if len(encoded_manifest.encode('utf-8')) > MAX_MANIFEST_BYTES:
            raise ValueError('checkpoint manifest exceeds byte limit')
        with ZipFile(staged,'w',ZIP_DEFLATED) as archive:
            archive.write(database,'research.sqlite')
            archive.writestr('manifest.json',encoded_manifest)
        _publish(staged,destination,_fault)
        return manifest


def _unpack_verified(checkpoint,root):
    checkpoint=Path(checkpoint)
    if checkpoint.stat().st_size > MAX_DATABASE_BYTES+MAX_MANIFEST_BYTES+1024*1024:
        raise ValueError('checkpoint archive exceeds byte limit')
    try:
        with ZipFile(checkpoint) as archive:
            members=archive.infolist()
            if len(members) != 2 or {m.filename for m in members} != {'manifest.json','research.sqlite'}:
                raise ValueError('checkpoint requires exactly two named members')
            for member in members:
                limit=MAX_DATABASE_BYTES if member.filename == 'research.sqlite' else MAX_MANIFEST_BYTES
                if member.file_size > limit or member.flag_bits & 1 or member.compress_type not in {ZIP_STORED,ZIP_DEFLATED}:
                    raise ValueError('unsupported or oversized checkpoint member')
                total=0
                with archive.open(member) as source, open(root/member.filename,'xb') as target:
                    for chunk in iter(lambda:source.read(1024*1024),b''):
                        total+=len(chunk)
                        if total > limit:raise ValueError('checkpoint member exceeds byte limit')
                        target.write(chunk)
        def unique_object(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('duplicate checkpoint manifest key')
                result[key]=value
            return result
        manifest=json.loads((root/'manifest.json').read_text(),object_pairs_hook=unique_object)
        database=root/'research.sqlite'
        if (set(manifest) != {'format','version','database_sha256','summary'}
                or manifest['format'] != 'double-diamond-checkpoint' or type(manifest['version']) is not int
                or manifest['version'] != 1 or manifest['database_sha256'] != _hash_file(database)):
            raise ValueError('checkpoint manifest/hash mismatch')
        if _encode(manifest['summary']) != _encode(_validate_database(database)):
            raise ValueError('checkpoint summary integrity mismatch')
        return manifest,database
    except (BadZipFile,sqlite3.DatabaseError,UnicodeError,KeyError,TypeError,AttributeError) as exc:
        raise ValueError('invalid checkpoint: '+str(exc)) from exc


def inspect_checkpoint(checkpoint):
    """Validate all content before returning the manifest; no database publication."""
    with tempfile.TemporaryDirectory(prefix='dd-inspect-') as temp:
        manifest,_=_unpack_verified(checkpoint,Path(temp))
        return manifest


def restore_checkpoint(checkpoint,destination,*,_fault=None):
    """Validate and publish a standalone database to a new path, never overwrite."""
    destination=_destination(destination)
    with tempfile.TemporaryDirectory(prefix='.dd-restore-',dir=destination.parent) as temp:
        manifest,database=_unpack_verified(checkpoint,Path(temp))
        _publish(database,destination,_fault)
        return manifest


class _ReadOnlySource:
    """Source adapter which cannot create a missing SQLite database or migrate it."""
    def __init__(self,path):
        self.path=Path(path).absolute()
        if not self.path.is_file():
            raise FileNotFoundError('source database does not exist: '+str(self.path))

    def _connect(self):
        db=sqlite3.connect(f'{self.path.as_uri()}?mode=ro',uri=True,timeout=5,isolation_level=None)
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA busy_timeout=5000')
        return db


def create_checkpoint_from_path(database,destination,*,expected_state_revision=None):
    """Create from an existing database without running store constructors/migrations."""
    return create_checkpoint(_ReadOnlySource(database),destination,expected_state_revision=expected_state_revision)


def verify_database(database):
    """Verify existing supported state/queue history read-only; no repair/adoption."""
    source=_ReadOnlySource(database)
    return _validate_database(source.path)
