
"""Cycle 99: end-to-end ResearchCycle integration.

This is an orchestration/integration harness. It does not retrieve live
evidence and does not treat synthetic evidence as real-world evidence.
"""
from dataclasses import dataclass, field, asdict
from typing import List

@dataclass
class CycleEvent:
    step: str
    status: str
    reason: str

@dataclass
class ResearchCycle:
    cycle_id: str
    question: str
    evidence_ids: List[str] = field(default_factory=list)
    hypothesis_ids: List[str] = field(default_factory=list)
    contradiction_ids: List[str] = field(default_factory=list)
    disposition_ids: List[str] = field(default_factory=list)
    events: List[CycleEvent] = field(default_factory=list)
    status: str = "started"
    synthetic_only: bool = True

    def record(self, step, status, reason):
        self.events.append(CycleEvent(step, status, reason))

    def complete(self, reason):
        self.status = "complete"
        self.record("cycle", "complete", reason)

    def pause_for_gate(self, reason):
        self.status = "human_gate_pending"
        self.record("cycle", "paused", reason)

    def export(self):
        if self.status not in {"complete", "human_gate_pending"}:
            raise ValueError("Cannot export an incomplete research cycle")
        return {
            "cycle_id": self.cycle_id,
            "question": self.question,
            "evidence_ids": self.evidence_ids,
            "hypothesis_ids": self.hypothesis_ids,
            "contradiction_ids": self.contradiction_ids,
            "disposition_ids": self.disposition_ids,
            "events": [asdict(e) for e in self.events],
            "status": self.status,
            "synthetic_only": self.synthetic_only,
        }
