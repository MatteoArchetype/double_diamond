
import pytest
from dd_research_runtime.cycle import ResearchCycle

def test_end_to_end_synthetic_cycle():
    c = ResearchCycle(
        "RC99-1",
        "Does AI-assisted workflow change managerial task composition?"
    )
    c.record("question", "accepted", "Question bounded.")
    c.record("hypothesis", "active", "Two competing explanations retained.")
    c.evidence_ids.extend(["SE1", "SE2"])
    c.hypothesis_ids.extend(["H1", "H2"])
    c.contradiction_ids.append("X1")
    c.disposition_ids.append("D1")
    c.record("evidence", "assessed", "Synthetic evidence only.")
    c.record("contradiction", "unresolved",
            "Two synthetic cases point in different directions.")
    c.complete("Remaining uncertainty does not justify an unqualified claim.")
    out = c.export()
    assert out["status"] == "complete"
    assert out["synthetic_only"] is True
    assert len(out["events"]) >= 5

def test_human_gate_interrupts_cycle():
    c = ResearchCycle("RC99-2", "Question")
    c.record("plan", "accepted", "Plan ready.")
    c.pause_for_gate("Primary research would be required to resolve the gap.")
    out = c.export()
    assert out["status"] == "human_gate_pending"

def test_incomplete_cycle_cannot_export():
    c = ResearchCycle("RC99-3", "Question")
    with pytest.raises(ValueError):
        c.export()
