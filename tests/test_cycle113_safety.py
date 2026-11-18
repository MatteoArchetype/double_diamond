import pytest
from dd_research_runtime.runtime import ResearchState
from dd_research_runtime.retrieval_validation import validate_retrieval_output, ingest_reviewed_retrieval
from dd_research_runtime.evidence_review import review_retrieval, ingest_with_review
from dataclasses import replace

D=dict(source_id='a',title='A',publisher='P',url='https://example.org/a',retrieved_at='2026-10-21',passage='passage A',content_location='sec A',provenance='publisher',independence_cluster='P')
def prepare(docs=None):
    docs = docs if docs is not None else [D]
    v=validate_retrieval_output('retrieve',dict(status='completed',documents=docs))
    snapshots={d['source_id']:dict(text=d['passage'],location=d['content_location']) for d in docs}
    r=review_retrieval(v,snapshots=snapshots,reviewer='reviewer-1',decision='approved',rationale='source checked')
    return v,r
AUTH=lambda name, permission: name=='reviewer-1' and permission=='evidence_ingest'
def test_legacy_bypass_disabled():
    v,_=prepare()
    with pytest.raises(PermissionError,match='legacy'): ingest_reviewed_retrieval(ResearchState(),v,approved=True)
def test_default_deny():
    v,r=prepare(); state=ResearchState()
    with pytest.raises(PermissionError,match='authorization'): ingest_with_review(state,v,r)
    assert not state.evidence

def test_unauthorized_reviewer():
    v,r=prepare()
    with pytest.raises(PermissionError): ingest_with_review(ResearchState(),v,r,authorize=lambda *_:False)
def test_tampered_review():
    v,r=prepare()
    with pytest.raises(ValueError,match='integrity'): ingest_with_review(ResearchState(),v,replace(r,reviewer='other'),authorize=lambda *_:True)
def test_atomic_rollback_when_second_document_fails():
    second={**D,'source_id':'b','url':'https://example.org/b','passage':'passage B','content_location':'sec B'}
    v,r=prepare([D,second]); state=ResearchState(); original=state.snapshot()
    original_add=ResearchState.add_evidence
    def fail_second(self, record):
        if record['evidence_id']=='b': raise RuntimeError('injected second-write failure')
        return original_add(self,record)
    ResearchState.add_evidence=fail_second
    try:
        with pytest.raises(RuntimeError,match='injected'): ingest_with_review(state,v,r,authorize=AUTH)
    finally: ResearchState.add_evidence=original_add
    assert state.snapshot()==original

def test_authorized_atomic_success():
    v,r=prepare(); state=ResearchState()
    assert len(ingest_with_review(state,v,r,authorize=AUTH))==1
    assert 'a' in state.sources and 'a' in state.evidence
