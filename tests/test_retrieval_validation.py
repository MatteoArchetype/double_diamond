import pytest
from dd_research_runtime.retrieval_validation import validate_retrieval_output, ingest_reviewed_retrieval, validate_execution_retrieval
from dd_research_runtime.action_executor import ExecutionResult

DOC = dict(source_id="s1",title="Title",publisher="Publisher",url="https://example.org/a",retrieved_at="2026-10-21",passage="Exact quoted context",content_location="section 2",provenance="publisher")
def test_completed_retrieval_is_review_only():
    result=validate_retrieval_output("retrieve",dict(status="completed",documents=[DOC]))
    assert result.status=="ready_for_review" and result.documents[0].source_id=="s1"
def test_nonretrieval_cannot_promote():
    assert validate_retrieval_output("search",dict(status="completed",documents=[DOC])).status=="not_retrieval"
def test_failed_execution_rejected():
    assert validate_retrieval_output("retrieve",dict(status="failed",documents=[DOC])).status=="rejected"
def test_missing_location_rejected():
    assert validate_retrieval_output("retrieve",dict(status="completed",documents=[{**DOC,"content_location":""}])).status=="rejected"
def test_synthetic_provenance_enforced():
    assert validate_retrieval_output("retrieve",dict(status="completed",documents=[{**DOC,"synthetic":True}])).status=="rejected"
def test_duplicate_sources_rejected():
    assert validate_retrieval_output("retrieve",dict(status="completed",documents=[DOC,DOC])).status=="rejected"
def test_all_or_nothing():
    assert validate_retrieval_output("retrieve",dict(status="completed",documents=[DOC,{"foo":"bar"}])).documents==()
def test_explicit_approval_required():
    v=validate_retrieval_output("retrieve",dict(status="completed",documents=[DOC]))
    with pytest.raises(PermissionError): ingest_reviewed_retrieval(object(),v,approved=False)
def test_unvalidated_rejected_even_with_approval():
    v=validate_retrieval_output("retrieve",dict(status="failed"))
    with pytest.raises(PermissionError): ingest_reviewed_retrieval(object(),v,approved=True)
def test_execution_adapter():
    ex=ExecutionResult("completed","retrieve",dict(status="completed",documents=[DOC]))
    assert validate_execution_retrieval(ex).status=="ready_for_review"
