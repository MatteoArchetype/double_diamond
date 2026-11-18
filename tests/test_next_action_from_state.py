from dd_research.next_action_from_state import summarize_state_for_next_action, derive_next_action_from_state, derive_and_record_next_action_from_state

class S:
    def __init__(self): self.evidence=[]; self.claims=[]; self.hypotheses=[]; self.contradictions=[]; self.changes=[]
    def _change(self,k,e,d): self.changes.append((k,e,d))
class C:
    def __init__(self): self.events=[]
    def record(self,k,s,d): self.events.append((k,s,d))
B={"question":"What should be tested next?","decision_relevance":"It may change the conclusion.","method_fit":"Retrieve the smallest missing evidence set."}

def test_empty_state_is_gap():
    x=summarize_state_for_next_action(S(),**B)
    assert x["evidence_gap"] and not x["unresolved_contradiction"]

def test_contradiction_is_preserved():
    s=S(); s.contradictions=[{"status":"unresolved","statement":"Sources disagree materially."}]
    x=summarize_state_for_next_action(s,**B)
    assert x["unresolved_contradiction"] and "Sources disagree materially." in x["contradiction"]

def test_empty_state_retrieves():
    assert derive_next_action_from_state(S(),**B)["highest_value_action"]=="retrieve"

def test_contradiction_audits():
    s=S(); s.evidence=[{"finding":"A"}]; s.claims=[{"statement":"C"}]; s.contradictions=[{"status":"open","statement":"Conflict"}]
    assert derive_next_action_from_state(s,**B)["highest_value_action"]=="audit"

def test_records_both_layers():
    s=S(); c=C(); a=derive_and_record_next_action_from_state(s,c,**B)
    assert a["highest_value_action"]=="retrieve" and s.changes[-1][0]=="next_action_decision" and c.events[-1][0]=="next_action"
