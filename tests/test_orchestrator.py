from dd_research_runtime.runtime import ResearchState
from dd_research_runtime.orchestrator import ResearchOrchestrator

def test_contradiction_gets_priority():
    s=ResearchState()
    s.add_claim({'claim_id':'A','claim_type':'descriptive','disposition':'retained','claim':'a'})
    s.add_claim({'claim_id':'B','claim_type':'descriptive','disposition':'retained','claim':'b'})
    s.add_contradiction({'contradiction_id':'X','claim_a':'A','claim_b':'B','disposition':'unresolved'})
    s.uncertainties['U']={'question':'q','status':'open'}
    d=ResearchOrchestrator(s).next_decision('c1','discover','x')
    assert d.decision=='investigate' and d.actions[0].action_type=='diagnose_contradiction'

def test_open_uncertainty_drives_discrimination():
    s=ResearchState(); s.uncertainties['U']={'question':'q','status':'open'}
    d=ResearchOrchestrator(s).next_decision('c1','discover','x')
    assert d.actions[0].action_type=='discriminate_claim'

def test_pending_gate_stops_progression():
    s=ResearchState(); s.create_gate('G','scope_change','change scope','material','approve')
    d=ResearchOrchestrator(s).next_decision('c1','define','x')
    assert d.decision=='human_gate'

def test_no_unresolved_stops():
    s=ResearchState(); d=ResearchOrchestrator(s).next_decision('c1','deliver','x')
    assert d.decision=='stop'
