from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from .runtime import ResearchState

@dataclass
class ResearchAction:
    action_id: str
    action_type: str
    objective: str
    rationale: str
    requires_gate: bool = False
    gate_type: str | None = None
    status: str = "proposed"
    outputs: List[str] = field(default_factory=list)

@dataclass
class OrchestrationDecision:
    cycle_id: str
    phase: str
    decision: str
    actions: List[ResearchAction]
    stop_reason: str | None = None

class ResearchOrchestrator:
    """Deterministic decision layer over ResearchState.

    It does not retrieve evidence or execute gated actions. It proposes the next
    smallest useful evidence/reasoning action and records why it was proposed.
    External adapters may execute non-gated actions and feed results back into
    ResearchState.
    """
    def __init__(self, state: ResearchState):
        self.state = state

    def _unresolved(self) -> List[Dict[str, Any]]:
        items=[]
        for cid,c in self.state.claims.items():
            if c.get("disposition") in {"unresolved", "unknown", "hypothesis"}:
                items.append({"id":cid,"kind":"claim","text":c.get("claim","")})
        for xid,x in self.state.contradictions.items():
            if x.get("disposition","unresolved") in {"unresolved", "open"}:
                items.append({"id":xid,"kind":"contradiction","text":x.get("issue", "")})
        for uid,u in self.state.uncertainties.items():
            if u.get("status","open") in {"open","unresolved"}:
                items.append({"id":uid,"kind":"uncertainty","text":u.get("question","")})
        return items

    def next_decision(self, cycle_id: str, phase: str, objective: str) -> OrchestrationDecision:
        unresolved=self._unresolved()
        pending_gates=[g for g in self.state.human_gates.values() if g.get("status")=="pending_review"]
        if pending_gates:
            return OrchestrationDecision(cycle_id,phase,"human_gate",[],"Pending human gate(s) block gated progression")
        if not unresolved:
            return OrchestrationDecision(cycle_id,phase,"stop",[],"No recorded unresolved claim, contradiction, or uncertainty")

        # Highest-value unresolved item first; contradictions outrank generic gaps.
        target=next((x for x in unresolved if x["kind"]=="contradiction"), unresolved[0])
        actions=[]
        if target["kind"]=="contradiction":
            actions.append(ResearchAction(
                f"{cycle_id}-diagnose-{target['id']}","diagnose_contradiction",
                f"Diagnose contradiction {target['id']}",
                "Resolve comparability before seeking additional volume of evidence."))
        else:
            actions.append(ResearchAction(
                f"{cycle_id}-discriminate-{target['id']}","discriminate_claim",
                f"Find evidence that could change belief about {target['id']}",
                "Prefer evidence with high potential to discriminate between competing explanations."))
        return OrchestrationDecision(cycle_id,phase,"investigate",actions)

    def propose_primary_research(self, cycle_id: str, objective: str, rationale: str) -> ResearchAction:
        action=ResearchAction(f"{cycle_id}-primary","primary_research",objective,rationale,True,"primary_research")
        self.state.create_gate(f"gate-{action.action_id}","primary_research",objective,rationale,"Approve primary research")
        return action

    def record_decision(self, decision: OrchestrationDecision):
        self.state.add_cycle({
            "cycle_id":decision.cycle_id,
            "phase":decision.phase,
            "objective":decision.actions[0].objective if decision.actions else decision.stop_reason or "",
            "status":"planned",
            "decision":decision.decision,
            "action_ids":[a.action_id for a in decision.actions],
        })
