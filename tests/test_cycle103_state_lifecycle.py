import pytest

from dd_research_runtime.runtime import ResearchState, ResearchInvariantError
from cycle_state import begin_cycle, complete_cycle, pause_cycle_for_gate
from research_pipeline import retrieve_to_state


def _doc(synthetic=True):
    from retrieval_adapter import RetrievedDocument
    return RetrievedDocument(
        source_id="source-103",
        title="Cycle 103 fixture",
        publisher="Test Fixture",
        url="https://example.org/cycle103",
        retrieved_at="2026-10-03T00:00:00Z",
        passage="A bounded fixture finding.",
        content_location="p. 2, paragraph 4",
        provenance="synthetic_test" if synthetic else "web",
        synthetic=synthetic,
        independence_cluster="cycle103-fixture",
    )


def test_cycle_completion_is_recorded_in_state():
    state = ResearchState(research_id="R103")
    cycle = begin_cycle(state, "RC103-1", "Synthetic question", "Developing", "Lifecycle test")
    cycle.evidence_ids.append("ev-103")
    cycle.record("evidence", "assessed", "Synthetic evidence only.")
    record = complete_cycle(state, cycle, "Developing", "Lifecycle test", "Bounded test complete.")
    assert record["status"] == "complete"
    assert record["synthetic_only"] is True
    assert state.research_cycles[-1]["status"] == "complete"
    assert state.research_cycles[-1]["evidence_ids"] == ["ev-103"]
    assert any(x["operation"] == "sync_cycle" for x in state.change_log)


def test_gate_pause_is_preserved():
    state = ResearchState(research_id="R103")
    cycle = begin_cycle(state, "RC103-2", "Synthetic question", "Developing", "Gate test")
    record = pause_cycle_for_gate(state, cycle, "Developing", "Gate test", "Primary research would be required.")
    assert record["status"] == "human_gate_pending"
    assert record["events"][-1]["status"] == "paused"


def test_synthetic_retrieval_normalizes_to_research_state():
    state = ResearchState(research_id="R103")
    evidence = retrieve_to_state(state, _doc(True), "ev-103")
    assert state.evidence["ev-103"]["exact_location"] == "p. 2, paragraph 4"
    assert evidence["evidence_id"] == "ev-103"
    assert state.evidence["ev-103"]["synthetic"] is True
    assert any(x["operation"] == "pipeline_retrieve_to_evidence" for x in state.change_log)


def test_non_synthetic_retrieval_registers_source():
    state = ResearchState(research_id="R103")
    evidence = retrieve_to_state(state, _doc(False), "ev-real-103")
    assert "source-103" in state.sources
    assert state.evidence["ev-real-103"]["exact_location"] == "p. 2, paragraph 4"
    assert evidence["synthetic"] is False


def test_duplicate_non_synthetic_source_preserves_invariant():
    state = ResearchState(research_id="R103")
    retrieve_to_state(state, _doc(False), "ev-dup-1")
    with pytest.raises(ResearchInvariantError):
        retrieve_to_state(state, _doc(False), "ev-dup-2")
