
from dd_research_runtime.stopping import StoppingAssessment, decide

def A(**kw):
    d = dict(
        decision_relevance="high",
        unresolved_uncertainties=["minor"],
        expected_information_gain="low",
        potential_to_change_conclusion="low",
        evidence_gap_materiality="low",
        human_gate_pending=False,
        rationale="Recorded because remaining uncertainty is unlikely to alter the decision."
    )
    d.update(kw)
    return StoppingAssessment(**d)

def test_stop_when_decision_sufficient():
    assert decide(A()) == "stop_decision_sufficient"

def test_continue_when_material_gap_could_change_conclusion():
    assert decide(A(
        evidence_gap_materiality="material",
        potential_to_change_conclusion="high"
    )) == "continue_targeted_research"

def test_continue_for_high_information_gain():
    assert decide(A(
        expected_information_gain="high",
        potential_to_change_conclusion="high"
    )) == "continue_targeted_research"

def test_human_gate_overrides_research_continuation():
    assert decide(A(
        human_gate_pending=True,
        expected_information_gain="high",
        potential_to_change_conclusion="high"
    )) == "escalate_human_gate"

def test_low_decision_relevance_can_stop():
    assert decide(A(
        decision_relevance="low",
        evidence_gap_materiality="low"
    )) == "stop_not_decision_relevant"

def test_ambiguous_case_escalates_judgement():
    assert decide(A(
        potential_to_change_conclusion="unknown",
        evidence_gap_materiality="moderate"
    )) == "escalate_human_judgement"
