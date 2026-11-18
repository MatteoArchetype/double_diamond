from __future__ import annotations

from typing import Any
from dd_research_runtime.cycle import ResearchCycle


def begin_cycle(state: Any, cycle_id: str, question: str, phase: str, objective: str) -> ResearchCycle:
    cycle = ResearchCycle(cycle_id, question)
    cycle.record("cycle", "started", objective)
    state.add_cycle({
        "cycle_id": cycle_id,
        "phase": phase,
        "objective": objective,
        "status": "started",
        "question": question,
        "synthetic_only": True,
    })
    state._change("begin_cycle", [cycle_id], objective)
    return cycle


def sync_cycle(state: Any, cycle: ResearchCycle, phase: str, objective: str) -> dict[str, Any]:
    exported = cycle.export()
    record = {
        "cycle_id": exported["cycle_id"],
        "phase": phase,
        "objective": objective,
        "status": exported["status"],
        "question": exported["question"],
        "evidence_ids": exported["evidence_ids"],
        "hypothesis_ids": exported["hypothesis_ids"],
        "contradiction_ids": exported["contradiction_ids"],
        "disposition_ids": exported["disposition_ids"],
        "events": exported["events"],
        "synthetic_only": exported["synthetic_only"],
    }
    state.add_cycle(record)
    state._change("sync_cycle", [cycle.cycle_id], cycle.status)
    return record


def complete_cycle(state: Any, cycle: ResearchCycle, phase: str, objective: str, reason: str) -> dict[str, Any]:
    cycle.complete(reason)
    return sync_cycle(state, cycle, phase, objective)


def pause_cycle_for_gate(state: Any, cycle: ResearchCycle, phase: str, objective: str, reason: str) -> dict[str, Any]:
    cycle.pause_for_gate(reason)
    return sync_cycle(state, cycle, phase, objective)
