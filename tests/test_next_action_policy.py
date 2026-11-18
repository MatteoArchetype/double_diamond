import pytest

from dd_research.next_action_policy import (
    derive_next_action,
    derive_and_record_next_action,
)


BASE = dict(
    question="Which uncertainty most affects the decision?",
    decision_relevance="The answer could change the research direction.",
    evidence="The current evidence is incomplete.",
    important_unknown="Whether the finding transfers.",
    method_fit="Use the smallest method that reduces the uncertainty.",
)


def test_human_gate_has_priority():
    a = derive_next_action(
        **BASE,
        human_gate_required=True,
        gate_reason="A consequential direction change requires review.",
        evidence_gap=True,
    )
    assert a["highest_value_action"] == "request_human_input"


def test_unresolved_contradiction_precedes_retrieval():
    a = derive_next_action(
        **BASE,
        contradiction="Two sources support materially different interpretations.",
        unresolved_contradiction=True,
        evidence_gap=True,
    )
    assert a["highest_value_action"] == "audit"


def test_stopping_condition_precedes_evidence_gap():
    a = derive_next_action(
        **BASE,
        stopping_satisfied=True,
        evidence_gap=True,
    )
    assert a["highest_value_action"] == "stop"


def test_evidence_gap_routes_to_retrieval():
    a = derive_next_action(
        **BASE,
        evidence_gap=True,
    )
    assert a["highest_value_action"] == "retrieve"


def test_default_routes_to_synthesis():
    a = derive_next_action(**BASE)
    assert a["highest_value_action"] == "synthesise"


class FakeState:
    def __init__(self):
        self.changes = []
    def _change(self, kind, evidence, detail):
        self.changes.append((kind, evidence, detail))


class FakeCycle:
    def __init__(self):
        self.events = []
    def record(self, kind, status, detail):
        self.events.append((kind, status, detail))


def test_derived_action_is_recorded_in_lifecycle():
    state, cycle = FakeState(), FakeCycle()
    a = derive_and_record_next_action(
        state=state,
        cycle=cycle,
        **BASE,
        evidence_gap=True,
    )
    assert a["highest_value_action"] == "retrieve"
    assert state.changes[-1][0] == "next_action_decision"
    assert cycle.events[-1][0] == "next_action"
