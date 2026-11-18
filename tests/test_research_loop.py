import pytest

from dd_research.research_loop import run_research_loop_step


class FakeState:
    def __init__(self):
        self.evidence = []
        self.claims = []
        self.hypotheses = []
        self.contradictions = []
        self.changes = []

    def _change(self, kind, evidence, detail):
        self.changes.append((kind, evidence, detail))


class FakeCycle:
    def __init__(self):
        self.events = []

    def record(self, kind, status, detail):
        self.events.append((kind, status, detail))


BASE = dict(
    question="Which uncertainty most affects the decision?",
    decision_relevance="The answer could change the research direction.",
    method_fit="Use the smallest method that reduces the uncertainty.",
)


def test_loop_step_derives_and_records_one_action():
    state, cycle = FakeState(), FakeCycle()
    action = run_research_loop_step(state, cycle, **BASE)
    assert action["highest_value_action"] == "retrieve"
    assert state.changes[-1][0] == "next_action_decision"
    assert cycle.events[-1][0] == "next_action"


def test_required_gate_routes_to_human():
    action = run_research_loop_step(
        FakeState(), FakeCycle(), **BASE,
        human_gate_required=True,
        gate_reason="A consequential direction change requires review.",
    )
    assert action["highest_value_action"] == "request_human_input"
    assert action["gate_required"] is True


def test_gate_requires_reason():
    with pytest.raises(ValueError, match="gate_reason"):
        run_research_loop_step(
            FakeState(), FakeCycle(), **BASE,
            human_gate_required=True,
        )


def test_stopping_condition_is_recorded_not_executed():
    state, cycle = FakeState(), FakeCycle()
    action = run_research_loop_step(
        state, cycle, **BASE, stopping_satisfied=True,
    )
    assert action["highest_value_action"] == "stop"
    assert state.changes[-1][0] == "next_action_decision"
    assert cycle.events[-1][1] == "stop"
    assert "execute" not in action
