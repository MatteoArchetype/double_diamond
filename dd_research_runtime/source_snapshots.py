"""Check caller-supplied snapshot content against the recorded review.

This verifies internal passage/location/hash consistency, not independent acquisition
or authenticity. Hosts must obtain the snapshots independently of executor text.
"""
from collections.abc import Mapping
from .evidence_review import _digest


def verify_source_snapshots(documents, review, snapshots, *, enforce_limits=True):
    if not isinstance(snapshots, Mapping):
        raise ValueError('source snapshots must be a mapping')
    ids=[doc['source_id'] for doc in documents]
    if set(snapshots) != set(ids):
        raise ValueError('source snapshot IDs must exactly match the batch')
    normalized={}
    total=0
    hashes=[]
    for doc in documents:
        sid=doc['source_id']
        value=snapshots[sid]
        if not isinstance(value, Mapping) or set(value) != {'text','location'}:
            raise ValueError('snapshot requires only text and location')
        text,location=value['text'],value['location']
        if not isinstance(text,str) or not isinstance(location,str):
            raise ValueError('snapshot text and location must be strings')
        if enforce_limits:
            from .payload_limits import check_snapshot
            total=check_snapshot(text,location,total)
        if doc['finding'] not in text or doc['location'] != location:
            raise ValueError('snapshot passage or exact location mismatch')
        normalized[sid]=dict(text=text,location=location)
        hashes.append(_digest(dict(source_id=sid,text=text,location=location)))
    if hashes != list(review['snapshot_digests']):
        raise ValueError('snapshot digest does not match review')
    return normalized
