import json
from dataclasses import replace

import pytest
from test_persistent_ingestion import store,batch,auth
from test_retrieval_validation import DOC
from test_pending_retrieval import queue
from dd_research_runtime import payload_limits as limits
from dd_research_runtime.retrieval_validation import validate_retrieval_output,RetrievalValidation
from dd_research_runtime.evidence_review import review_retrieval
from retrieval_adapter import RetrievedDocument


def validate(docs):
    return validate_retrieval_output('retrieve',dict(status='completed',documents=docs))


def raw_docs(count):
    return [{**DOC,'source_id':str(i),'url':'https://example.org/'+str(i)} for i in range(count)]


def test_document_count_exact_and_over_limit():
    assert validate(raw_docs(limits.MAX_DOCUMENTS)).status == 'ready_for_review'
    result=validate(raw_docs(limits.MAX_DOCUMENTS+1))
    assert result.status == 'rejected' and result.documents == ()
    assert 'count' in result.errors[0]


@pytest.mark.parametrize('field,limit',[('title',limits.MAX_FIELD_BYTES),('passage',limits.MAX_PASSAGE_BYTES)])
def test_string_size_exact_and_over_without_truncation(field,limit):
    exact='x'*limit
    result=validate([{**DOC,field:exact}])
    assert result.status == 'ready_for_review'
    assert getattr(result.documents[0],field) == exact
    over=validate([{**DOC,field:exact+'x'}])
    assert over.status == 'rejected' and not over.documents


def test_utf8_bytes_are_measured_not_character_count():
    exact='æ'*(limits.MAX_FIELD_BYTES//2)
    assert validate([{**DOC,'title':exact}]).status == 'ready_for_review'
    assert validate([{**DOC,'title':exact+'æ'}]).status == 'rejected'


def test_metadata_uses_canonical_json_bytes():
    empty_size=len(json.dumps({'value':''},ensure_ascii=False,separators=(',',':')).encode())
    exact={'value':'x'*(limits.MAX_METADATA_BYTES-empty_size)}
    assert validate([{**DOC,'metadata':exact}]).status == 'ready_for_review'
    exact['value']+='x'
    assert validate([{**DOC,'metadata':exact}]).status == 'rejected'


def test_batch_limit_rejects_individually_valid_documents():
    docs=raw_docs(33)
    for d in docs:d['passage']='x'*limits.MAX_PASSAGE_BYTES
    result=validate(docs)
    assert result.status == 'rejected' and not result.documents
    assert 'batch' in result.errors[0]


def test_single_oversized_document_rejects_entire_batch():
    result=validate([DOC,{**DOC,'source_id':'second','passage':'x'*(limits.MAX_PASSAGE_BYTES+1)}])
    assert result.status == 'rejected' and not result.documents


def test_manual_ready_status_cannot_bypass_batch_count():
    docs=tuple(RetrievedDocument(**d) for d in raw_docs(limits.MAX_DOCUMENTS+1))
    v=RetrievalValidation('ready_for_review',docs,())
    with pytest.raises(ValueError,match='count'):
        review_retrieval(v,snapshots={},reviewer='human',decision='approved',rationale='Check')


def test_direct_persistent_ingestion_checks_count_before_mutation(store):
    _,r=batch()
    docs=tuple(RetrievedDocument(**d) for d in raw_docs(limits.MAX_DOCUMENTS+1))
    with pytest.raises(ValueError,match='count'):
        store.ingest(RetrievalValidation('ready_for_review',docs,()),r,operation_id='oversize',
                     expected_state_revision=0,expected_ledger_revision=0,authorize=auth)
    assert store.load()[1] == store.ledger.revision() == 0
    assert store.review_coverage()['retained_reviews'] == 0


def snapshots(v,extra=''):
    return {d.source_id:dict(text=d.passage+extra,location=d.content_location) for d in v.documents}


def review(v,raw):
    return review_retrieval(v,snapshots=raw,reviewer='human',decision='approved',rationale='Fixture checked')


def test_snapshot_exact_boundary_and_oversize(monkeypatch):
    v,_=batch();raw=snapshots(v,' context')
    size=len(raw['s1']['text'].encode())+len(raw['s1']['location'].encode())
    monkeypatch.setattr(limits,'MAX_SNAPSHOT_BYTES',size)
    assert review(v,raw).decision == 'approved'
    raw['s1']['text']+='x'
    with pytest.raises(ValueError,match='snapshot.*byte limit'):review(v,raw)


def test_snapshot_batch_exact_and_over_boundary(monkeypatch):
    first,_=batch('s1');second,_=batch('s2')
    v=replace(first,documents=first.documents+second.documents)
    raw=snapshots(v)
    total=sum(len(x['text'].encode())+len(x['location'].encode()) for x in raw.values())
    monkeypatch.setattr(limits,'MAX_SNAPSHOT_BATCH_BYTES',total)
    assert review(v,raw).decision == 'approved'
    monkeypatch.setattr(limits,'MAX_SNAPSHOT_BATCH_BYTES',total-1)
    with pytest.raises(ValueError,match='snapshot batch'):review(v,raw)


def test_full_snapshot_retention_rechecks_limit_before_commit(store,monkeypatch):
    v,_=batch();raw=snapshots(v,' independent full context');r=review(v,raw)
    monkeypatch.setattr(limits,'MAX_SNAPSHOT_BYTES',len(v.documents[0].passage))
    with pytest.raises(ValueError,match='snapshot'):
        store.ingest(v,r,operation_id='too-large',expected_state_revision=0,expected_ledger_revision=0,
                     authorize=auth,source_snapshots=raw)
    assert store.snapshot_coverage()['retained_snapshot_sets'] == 0
    assert store.load()[1] == store.ledger.revision() == 0


def test_committed_snapshot_history_not_retroactively_rejected(store,monkeypatch):
    v,_=batch();raw=snapshots(v,' retained source context');r=review(v,raw)
    store.ingest(v,r,operation_id='snapshot',expected_state_revision=0,expected_ledger_revision=0,
                 authorize=auth,source_snapshots=raw)
    monkeypatch.setattr(limits,'MAX_SNAPSHOT_BYTES',1)
    assert store.load_source_snapshots('snapshot') == raw
    assert store.load()[1] == 1
    assert store.snapshot_coverage()['retained_snapshot_sets'] == 1


def test_existing_queued_oversize_record_fails_without_rewriting(queue,monkeypatch):
    import sqlite3
    with sqlite3.connect(queue.store.ledger.path) as db:
        before=db.execute('SELECT payload,digest FROM pending_retrievals').fetchone()
    monkeypatch.setattr(limits,'MAX_PASSAGE_BYTES',1)
    with pytest.raises(ValueError,match='candidate not reviewable'):queue.load('candidate')
    with sqlite3.connect(queue.store.ledger.path) as db:
        assert db.execute('SELECT payload,digest FROM pending_retrievals').fetchone() == before


def test_synthetic_inputs_do_not_bypass_limits():
    result=validate([{**DOC,'synthetic':True,'provenance':'synthetic','passage':'x'*(limits.MAX_PASSAGE_BYTES+1)}])
    assert result.status == 'rejected' and not result.documents


def test_escaped_json_counts_encoded_bytes(monkeypatch):
    metadata={'value':'\n'*20}
    canonical=len(json.dumps(metadata,ensure_ascii=False,separators=(',',':')).encode())
    monkeypatch.setattr(limits,'MAX_METADATA_BYTES',canonical)
    assert validate([{**DOC,'metadata':metadata}]).status == 'ready_for_review'
    monkeypatch.setattr(limits,'MAX_METADATA_BYTES',canonical-1)
    assert validate([{**DOC,'metadata':metadata}]).status == 'rejected'
