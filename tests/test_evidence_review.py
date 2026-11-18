import pytest
from dd_research_runtime.retrieval_validation import validate_retrieval_output
from dd_research_runtime.evidence_review import review_retrieval, ingest_with_review
from dd_research_runtime.runtime import ResearchState
AUTH = lambda reviewer, permission: reviewer in {"r", "reviewer-1"} and permission == "evidence_ingest"

DOC = dict(source_id='s1', title='Title', publisher='Publisher', url='https://example.org/a',
           retrieved_at='2026-10-21', passage='Exact quoted context', content_location='section 2',
           provenance='publisher', independence_cluster='publisher-original')
def validation(docs=None):
    return validate_retrieval_output('retrieve', {'status':'completed','documents': docs or [DOC]})
def review(v, **kwargs):
    return review_retrieval(v, snapshots={'s1':{'text':'Prefix Exact quoted context suffix','location':'section 2'}},
                            reviewer='reviewer-1',decision='approved',rationale='Checked snapshot',**kwargs)
def test_verified_review():
    assert review(validation()).decision == 'approved'
def test_passage_mismatch():
    with pytest.raises(ValueError, match='not verified'):
        review_retrieval(validation(),snapshots={'s1':{'text':'unrelated','location':'section 2'}},reviewer='r',decision='approved',rationale='x')
def test_locator_mismatch():
    with pytest.raises(ValueError, match='not verified'):
        review_retrieval(validation(),snapshots={'s1':{'text':'Exact quoted context','location':'section 3'}},reviewer='r',decision='approved',rationale='x')
def test_missing_snapshot():
    with pytest.raises(ValueError, match='missing'):
        review_retrieval(validation(),snapshots={},reviewer='r',decision='approved',rationale='x')
def test_missing_reviewer():
    with pytest.raises(ValueError, match='reviewer'):
        review_retrieval(validation(),snapshots={'s1':{'text':'Exact quoted context','location':'section 2'}},reviewer='',decision='approved',rationale='x')
def test_duplicate_in_batch():
    d2={**DOC,'source_id':'s2'}
    with pytest.raises(ValueError, match='duplicate'):
        review_retrieval(validation([DOC,d2]),snapshots={k:{'text':'Exact quoted context','location':'section 2'} for k in ['s1','s2']},reviewer='r',decision='approved',rationale='x')
def test_rejected_review_not_ingested():
    v=validation()
    r=review_retrieval(v,snapshots={'s1':{'text':'Exact quoted context','location':'section 2'}},reviewer='r',decision='rejected',rationale='not sufficient')
    with pytest.raises(PermissionError): ingest_with_review(ResearchState(),v,r,authorize=AUTH)
def test_ingest_approved():
    v=validation(); s=ResearchState()
    result=ingest_with_review(s,v,review(v),authorize=AUTH)
    assert len(result)==1 and 's1' in s.evidence and 's1' in s.sources
    assert any(x['operation']=='evidence_review' for x in s.change_log)
def test_no_repeat_ingestion():
    v=validation(); s=ResearchState(); r=review(v)
    ingest_with_review(s,v,r,authorize=AUTH)
    with pytest.raises(ValueError, match='duplicate'): ingest_with_review(s,v,r,authorize=AUTH)
def test_changed_batch_not_authorized():
    v=validation(); r=review(v)
    altered=validation([{**DOC,'passage':'Other'}])
    with pytest.raises(ValueError, match='does not match'): ingest_with_review(ResearchState(),altered,r,authorize=AUTH)
def test_preexisting_duplicate_detected():
    v=validation(); s=ResearchState(); ingest_with_review(s,v,review(v),authorize=AUTH)
    with pytest.raises(ValueError,match='duplicate'):
        review_retrieval(v,snapshots={'s1':{'text':'Exact quoted context','location':'section 2'}},reviewer='r',decision='approved',rationale='x',state=s)
