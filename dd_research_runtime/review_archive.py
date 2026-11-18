"""Full approved review/request retention for ingestion after explicit adoption.

A migration boundary distinguishes missing legacy records from corruption in new
writes. Neither the marker nor the records are signatures or external anchors.
"""
import json
from .persistent_ingestion import _encode, _checksum
from .evidence_review import _digest


def initialize_archive(db):
    with db:
        db.execute('BEGIN IMMEDIATE')
        had_policy = bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_archive_policy'").fetchone())
        had_archive = bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ingestion_review_archive'").fetchone())
        if had_policy != had_archive:
            raise ValueError('review archive schema integrity mismatch')
        db.execute('CREATE TABLE IF NOT EXISTS review_archive_policy (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, digest TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS ingestion_review_archive (operation_id TEXT PRIMARY KEY REFERENCES ingestion_operations(operation_id), payload TEXT NOT NULL, digest TEXT NOT NULL)')
        if not db.execute('SELECT 1 FROM review_archive_policy WHERE id=1').fetchone():
            if had_policy:
                raise ValueError('missing review archive policy integrity mismatch')
            row=db.execute('SELECT revision FROM research_state WHERE id=1').fetchone()
            encoded=_encode(dict(version=1,legacy_state_revision=row[0] if row else 0))
            db.execute('INSERT INTO review_archive_policy VALUES (1,?,?)',(encoded,_checksum(encoded)))


def boundary(db):
    row=db.execute('SELECT payload,digest FROM review_archive_policy WHERE id=1').fetchone()
    try:
        if row is None or _checksum(row[0]) != row[1]:
            raise ValueError('policy checksum mismatch')
        data=json.loads(row[0])
        value=data['legacy_state_revision']
        if data['version'] != 1 or type(value) is not int or value < 0:
            raise ValueError('invalid archive policy')
        return value
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('review archive policy integrity mismatch: '+str(exc)) from exc


def retain(db,operation_id,request_payload):
    encoded=_encode(request_payload)
    db.execute('INSERT INTO ingestion_review_archive VALUES (?,?,?)',(operation_id,encoded,_checksum(encoded)))


def verify_archive(db,operations):
    legacy_boundary=boundary(db)
    archive=dict((oid,(payload,digest)) for oid,payload,digest in db.execute('SELECT operation_id,payload,digest FROM ingestion_review_archive'))
    operations_by_id={row[0]:row for row in operations}
    if set(archive)-set(operations_by_id):
        raise ValueError('orphan review archive integrity mismatch')
    revisions=[]
    legacy=0
    for oid,request_digest,review_digest,result_encoded,_ in operations:
        result=json.loads(result_encoded)
        revision=result['state_revision']
        revisions.append(revision)
        row=archive.get(oid)
        if revision <= legacy_boundary:
            if row is not None:
                raise ValueError('legacy review archive coverage integrity mismatch')
            legacy+=1
            continue
        if row is None:
            raise ValueError('missing review archive integrity mismatch')
        encoded,digest=row
        try:
            if _checksum(encoded) != digest or digest != request_digest:
                raise ValueError('request checksum mismatch')
            data=json.loads(encoded)
            if set(data) not in ({'review','status','documents'}, {'review','status','documents','source_snapshots'}) or data['status'] != 'ready_for_review':
                raise ValueError('invalid retained request')
            review=data['review']
            expected={'batch_digest','reviewer','decision','rationale','snapshot_digests','duplicate_keys','record_digest'}
            if set(review) not in (expected,expected|{'candidate_context'}):
                raise ValueError('invalid review fields')
            base={k:v for k,v in review.items() if k != 'record_digest'}
            docs=data['documents']
            if (review['record_digest'] != review_digest or _digest(base) != review_digest
                    or review['decision'] != 'approved' or review['duplicate_keys'] != []
                    or not isinstance(docs,list) or not docs
                    or review['batch_digest'] != _digest(docs)
                    or not isinstance(review['snapshot_digests'],list)
                    or len(review['snapshot_digests']) != len(docs)):
                raise ValueError('review or batch mismatch')
            if 'source_snapshots' in data:
                from .source_snapshots import verify_source_snapshots
                verify_source_snapshots(docs,review,data['source_snapshots'],enforce_limits=False)
            receipt=db.execute('SELECT batch_digest,reviewer,decision,rationale FROM receipts WHERE review_digest=?',(review_digest,)).fetchone()
            if receipt != (review['batch_digest'],review['reviewer'],'approved',review['rationale']):
                raise ValueError('receipt details mismatch')
            normalized=[dict(evidence_id=d['source_id'],source_id=d['source_id'],finding=d['finding'],
                             exact_location=d['location'],provenance=d['provenance'],synthetic=d['synthetic'],
                             independence_cluster=d['independence_cluster'],metadata=d['metadata']) for d in docs]
            if normalized != result['evidence']:
                raise ValueError('retained documents differ from evidence')
            # Bind new queue approvals to their recorded renewal lineage, if any.
            has_queue=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pending_retrievals'").fetchone()
            if has_queue:
                candidate=db.execute('SELECT candidate_id FROM pending_retrievals WHERE operation_id=?',(oid,)).fetchone()
                if candidate:
                    has_lineage=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_renewals'").fetchone()
                    link=db.execute('SELECT digest FROM candidate_renewals WHERE child_id=?',candidate).fetchone() if has_lineage else None
                    context=review.get('candidate_context','')
                    if context != (link[0] if link else ''):
                        raise ValueError('retained renewal context mismatch')
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError('review archive integrity mismatch: '+str(exc)) from exc
    if legacy_boundary > max(revisions,default=0):
        raise ValueError('review archive boundary integrity mismatch')
    return dict(legacy_operations=legacy,retained_reviews=len(archive),legacy_state_revision=legacy_boundary)
