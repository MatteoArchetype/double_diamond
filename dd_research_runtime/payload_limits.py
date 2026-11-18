"""Explicit source-input limits; oversize data is rejected, never truncated.

These are application policies for materialized Python inputs, not a network,
process-memory, historical-database or external-executor resource sandbox.
"""
import json

MAX_DOCUMENTS = 100
MAX_FIELD_BYTES = 8 * 1024
MAX_PASSAGE_BYTES = 64 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_BATCH_BYTES = 2 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 1024 * 1024
MAX_SNAPSHOT_BATCH_BYTES = 8 * 1024 * 1024


def text_bytes(value, limit, label):
    if len(value) > limit:
        raise ValueError(label+' exceeds byte limit')
    size=len(value.encode('utf-8'))
    if size > limit:
        raise ValueError(label+' exceeds byte limit')
    return size


def json_bytes(value, limit, label):
    total=0
    encoder=json.JSONEncoder(sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    for part in encoder.iterencode(value):
        total+=text_bytes(part,limit,label)
        if total > limit:
            raise ValueError(label+' exceeds byte limit')
    return total


def check_document(fields, metadata):
    for key,value in fields.items():
        text_bytes(value,MAX_PASSAGE_BYTES if key == 'passage' else MAX_FIELD_BYTES,'document '+key)
    json_bytes(metadata,MAX_METADATA_BYTES,'document metadata')


def checked_payloads(documents):
    if not documents or len(documents) > MAX_DOCUMENTS:
        raise ValueError('retrieval document count exceeds limit or is empty')
    payloads=[doc.to_evidence_payload() for doc in documents]
    json_bytes(payloads,MAX_BATCH_BYTES,'retrieval batch')
    return payloads


def check_snapshot(text,location,total):
    size=text_bytes(text,MAX_SNAPSHOT_BYTES,'source snapshot')
    size+=text_bytes(location,MAX_FIELD_BYTES,'snapshot location')
    if size > MAX_SNAPSHOT_BYTES:
        raise ValueError('source snapshot exceeds byte limit')
    total+=size
    if total > MAX_SNAPSHOT_BATCH_BYTES:
        raise ValueError('source snapshot batch exceeds byte limit')
    return total
