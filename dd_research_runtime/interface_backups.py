"""Bounded private-session checkpoint transport; restores publish a separate case.

Integrity verification is not authentication of sources, reviewers or earlier approvals.
"""
import hashlib
import os
import tempfile
import uuid
from collections import Counter
from contextlib import closing
from pathlib import Path
from .checkpoints import restore_checkpoint,create_checkpoint_from_path,_ReadOnlySource
from .persistent_ingestion import PersistentEvidenceStore,_encode
from .review_ledger import ReviewLedger

MAX_TRANSFER_BYTES=32*1024*1024


def _payload(data):
    if type(data) is not bytes or not 0<len(data)<=MAX_TRANSFER_BYTES:raise ValueError('Choose a checkpoint ZIP no larger than 32 MiB.')
    return hashlib.sha256(data).hexdigest()


def _read_state(database):
    store=object.__new__(PersistentEvidenceStore);store.ledger=object.__new__(ReviewLedger);store.ledger.path=str(database)
    with closing(_ReadOnlySource(database)._connect()) as db:
        db.execute('BEGIN');return store._verify_integrity(db)


def _unpack(data,root):
    digest=_payload(data);archive=root/'upload.zip';archive.write_bytes(data)
    folder=root/'case';folder.mkdir(mode=0o700)
    # restore_checkpoint verifies the archive and publishes the database itself; the
    # returned manifest is not needed here because the preview is read from state.
    restore_checkpoint(archive,folder/'research.sqlite')
    state,sr,lr,_=_read_state(folder/'research.sqlite')
    workflow=getattr(state,'workflow',{})
    if workflow.get('workflow_version')!=3:raise ValueError('The browser can restore criterion-linked Double Diamond cases only. Use the checkpoint tools for earlier workflow formats.')
    title=state.research_id if isinstance(state.research_id,str) and state.research_id.strip() else 'Research case'
    synthetic=sum(e.get('synthetic') is True for e in state.evidence.values())
    preview=dict(checkpoint_digest=digest,title=title[:400],state_revision=sr,ledger_revision=lr,phase=workflow['phase'],status=workflow['status'],
        evidence_counts=dict(synthetic=synthetic,source_records=len(state.evidence)-synthetic),
        historical_gate_counts=dict(Counter(g.get('status','unknown') for g in state.human_gates.values())),
        historical_acceptance_entries=len(getattr(state,'acceptance_records',{})),
        integrity_verified=True,identity_authenticated=False,approval_granted=False,restores_as_separate_case=True)
    return folder,preview


def inspect_upload(data):
    with tempfile.TemporaryDirectory(prefix='dd-ui-inspect-') as temp:
        _,preview=_unpack(data,Path(temp));return preview


def restore_upload(workspace,data,*,expected_digest,_fault=None):
    digest=_payload(data)
    if not isinstance(expected_digest,str) or len(expected_digest)!=64 or any(c not in '0123456789abcdef' for c in expected_digest):raise ValueError('Inspect this checkpoint before confirming restore.')
    if digest!=expected_digest:raise ValueError('The checkpoint changed after inspection. Inspect the selected file again.')
    workspace=Path(workspace).absolute()
    if not workspace.is_dir() or workspace.is_symlink():raise ValueError('invalid restore workspace')
    def fault(name):
        if _fault is not None:_fault(name)
    destination=None;reserved_inode=None;published=False
    with tempfile.TemporaryDirectory(prefix='.restore-',dir=workspace) as temp:
        staged,preview=_unpack(data,Path(temp));fault('after_verification')
        cid=uuid.uuid4().hex;destination=workspace/cid
        # Reserve a fresh name exclusively. Publication replaces only our empty reservation.
        destination.mkdir(mode=0o700);reserved_inode=destination.stat().st_ino
        try:
            counts=preview['evidence_counts']
            metadata=dict(title='Restored · '+preview['title'],synthetic_example=False,restored_checkpoint=True,
                synthetic_only=counts['synthetic']>0 and counts['source_records']==0,checkpoint_digest=digest)
            meta=staged/'case-info.json';meta.write_text(_encode(metadata));os.chmod(meta,0o600)
            fault('before_publication')
            if destination.is_symlink() or destination.stat().st_ino!=reserved_inode:raise ValueError('restore reservation changed')
            os.replace(staged,destination);published=True
            fault('after_publication')
            return dict(case_id=cid,restored_checkpoint=True,approval_granted=False,checkpoint_digest=digest)
        finally:
            # Never delete or roll back a published case, including an uncertain response.
            if not published and destination is not None and destination.is_dir() and not destination.is_symlink() and destination.stat().st_ino==reserved_inode:
                try:destination.rmdir()
                except OSError:pass


def download_checkpoint(database,*,expected_revision):
    if type(expected_revision) is not int or expected_revision<0:raise ValueError('A current case revision is required.')
    with tempfile.TemporaryDirectory(prefix='dd-ui-backup-') as temp:
        target=Path(temp)/'research-checkpoint.zip'
        manifest=create_checkpoint_from_path(database,target,expected_state_revision=expected_revision)
        if target.stat().st_size>MAX_TRANSFER_BYTES:raise ValueError('This checkpoint exceeds the browser 32 MiB limit. Use the documented checkpoint tools.')
        return target.read_bytes(),manifest
