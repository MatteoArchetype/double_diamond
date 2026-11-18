import sqlite3
import pytest
from dd_research_runtime.review_ledger import ReviewLedger
from dd_research_runtime.evidence_review import review_retrieval
from dd_research_runtime.retrieval_validation import validate_retrieval_output

DOC=dict(source_id="s1",title="T",publisher="P",url="https://example.org",retrieved_at="2026-10-21",passage="Passage",content_location="p1",provenance="publisher",independence_cluster="p")
def make_review(decision="approved"):
    v=validate_retrieval_output("retrieve",{"status":"completed","documents":[DOC]})
    return review_retrieval(v,snapshots={"s1":{"text":"Passage", "location":"p1"}},reviewer="r",decision=decision,rationale="verified")

def test_ledger_initial(tmp_path):
    ledger=ReviewLedger(tmp_path/"reviews.db")
    assert ledger.revision()==0 and ledger.verify()
def test_ledger_append_persist(tmp_path):
    path=tmp_path/"reviews.db"; ledger=ReviewLedger(path)
    assert ledger.append(make_review(),expected_revision=0)["revision"]==1
    assert ReviewLedger(path).revision()==1 and ReviewLedger(path).verify()
def test_ledger_stale_revision(tmp_path):
    ledger=ReviewLedger(tmp_path/"reviews.db"); ledger.append(make_review(),expected_revision=0)
    with pytest.raises(RuntimeError,match="stale"):ledger.append(make_review("rejected"),expected_revision=0)
def test_ledger_duplicate_digest(tmp_path):
    ledger=ReviewLedger(tmp_path/"reviews.db"); ledger.append(make_review(),expected_revision=0)
    with pytest.raises(sqlite3.IntegrityError):ledger.append(make_review(),expected_revision=1)
    assert ledger.revision()==1
def test_ledger_tampering_detected(tmp_path):
    path=tmp_path/"reviews.db"; ledger=ReviewLedger(path);ledger.append(make_review(),expected_revision=0)
    with sqlite3.connect(path) as db:db.execute("UPDATE receipts SET rationale='altered'")
    assert not ledger.verify()
def test_ledger_rejected_review_recordable(tmp_path):
    ledger=ReviewLedger(tmp_path/"reviews.db");ledger.append(make_review("rejected"),expected_revision=0)
    assert ledger.verify() and ledger.receipts()[0][3]=="rejected"
def test_ledger_bad_revision(tmp_path):
    ledger=ReviewLedger(tmp_path/"reviews.db")
    with pytest.raises(ValueError):ledger.append(make_review(),expected_revision=True)
