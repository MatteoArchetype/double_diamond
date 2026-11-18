"""Read-only, pinned inspection of retained intake context. Never source authentication."""
import copy
import json
from contextlib import closing
from .checkpoints import _ReadOnlySource
from .persistent_ingestion import PersistentEvidenceStore
from .review_ledger import ReviewLedger


def read_source(database,evidence_id,*,expected_revision,_after_pin=None):
    if not isinstance(evidence_id,str) or not evidence_id or len(evidence_id)>256:raise ValueError('invalid evidence identifier')
    if type(expected_revision) is not int or expected_revision<0:raise ValueError('A current case revision is required.')
    source=_ReadOnlySource(database)
    store=object.__new__(PersistentEvidenceStore);store.ledger=object.__new__(ReviewLedger);store.ledger.path=str(source.path)
    with closing(source._connect()) as db:
        db.execute('BEGIN')
        state,sr,lr,_=store._verify_integrity(db)
        if sr!=expected_revision:raise RuntimeError('This case changed. Refresh saved research before inspecting source context.')
        if _after_pin is not None:_after_pin()
        evidence=state.evidence.get(evidence_id)
        if evidence is None:raise ValueError('unknown retained evidence')
        result=dict(evidence=evidence,state_revision=sr,ledger_revision=lr,context_status='unavailable',snapshot=None,review=None,operation_id=None,
                    boundary='Retained intake text and review are audit records, not independent proof of source authenticity, acquisition or reviewer identity.')
        matches=[]
        for oid,encoded in db.execute('SELECT operation_id,result FROM ingestion_operations'):
            retained=[e for e in json.loads(encoded)['evidence'] if e['evidence_id']==evidence_id]
            if retained:
                if len(retained)!=1 or retained[0]!=evidence:raise ValueError('retained evidence receipt mismatch')
                matches.append(oid)
        if len(matches)>1:raise ValueError('ambiguous source intake history')
        if matches:
            oid=matches[0];result['operation_id']=oid
            row=db.execute('SELECT payload FROM ingestion_review_archive WHERE operation_id=?',(oid,)).fetchone()
            if row:
                payload=json.loads(row[0]);result['review']=payload['review'];result['context_status']='review_only'
                snapshots=payload.get('source_snapshots',{})
                if evidence['source_id'] in snapshots:
                    result.update(context_status='retained_snapshot',snapshot=snapshots[evidence['source_id']])
        return copy.deepcopy(result)
