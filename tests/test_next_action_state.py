import pytest
from dd_research.next_action_state import make_next_action, record_next_action, record_next_action_in_cycle

class FakeState:
    def __init__(self): self.changes=[]
    def _change(self, kind, evidence, detail): self.changes.append((kind,evidence,detail))
class FakeCycle:
    def __init__(self): self.events=[]
    def record(self, kind, status, detail): self.events.append((kind,status,detail))

def base_action(**overrides):
    v=dict(question="What uncertainty most affects the decision?", decision_relevance="It could change the recommended direction.", evidence="Current evidence is incomplete.", important_unknown="Whether the observed effect transfers.", contradiction=None, highest_value_action="test", method_fit="A bounded test best reduces the uncertainty.", gate_required=False, gate_reason=None)
    v.update(overrides); return v

def test_next_action_requires_context():
    with pytest.raises(ValueError): make_next_action(**base_action(question=""))
def test_next_action_rejects_unknown_action():
    with pytest.raises(ValueError): make_next_action(**base_action(highest_value_action="invent"))
def test_gate_routes_to_human_input():
    a=make_next_action(**base_action(highest_value_action="request_human_input", gate_required=True, gate_reason="Human review is required."))
    assert a["gate_required"] is True and a["highest_value_action"] == "request_human_input"
def test_gate_requires_reason():
    with pytest.raises(ValueError): make_next_action(**base_action(highest_value_action="request_human_input", gate_required=True, gate_reason=None))
def test_gate_cannot_be_bypassed_by_other_action():
    with pytest.raises(ValueError): make_next_action(**base_action(highest_value_action="search", gate_required=True, gate_reason="Human review is required."))
def test_record_next_action_writes_audit_event():
    s=FakeState(); a=make_next_action(**base_action()); record_next_action(s,a); assert s.changes[-1][0] == "next_action_decision" and s.changes[-1][2]["highest_value_action"] == "test"
def test_record_next_action_in_cycle_writes_both_layers():
    s=FakeState(); c=FakeCycle(); a=make_next_action(**base_action(highest_value_action="audit")); record_next_action_in_cycle(s,c,a); assert s.changes[-1][0] == "next_action_decision"; assert c.events[-1][0:2] == ("next_action","audit")
