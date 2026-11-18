"""Allow-listed execution boundary; executor output is not verified evidence."""
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

EXECUTABLE_ACTIONS = {"search", "retrieve", "compare", "audit", "test", "reframe", "synthesise"}
SUPPORTED_STATUSES = {"completed", "failed", "needs_human_review", "no_result"}

@dataclass
class ExecutionResult:
    status: str
    action: str
    output: Any = None
    reason: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)

def execute_registered_action(state: Any, cycle: Any, decision: Mapping[str, Any], *,
                              executors: Mapping[str, Callable[..., Any]],
                              context: Mapping[str, Any] | None = None) -> ExecutionResult:
    """Execute at most one explicitly registered action.

    Human-gated actions never invoke an executor. Returned data is logged as
    execution metadata only; this function never creates evidence records.
    """
    if not isinstance(decision, Mapping):
        raise TypeError("decision must be a mapping")
    action = decision.get("highest_value_action")
    if decision.get("gate_required") or action == "request_human_input":
        return ExecutionResult("paused_for_human", str(action),
            reason=str(decision.get("gate_reason") or "Human approval required."))
    if action == "stop":
        return ExecutionResult("stopped", "stop", reason="Decision policy requested stop.")
    if action not in EXECUTABLE_ACTIONS:
        raise ValueError(f"action is not executable: {action}")
    executor = executors.get(action)
    if not callable(executor):
        raise ValueError(f"no executor registered for action: {action}")
    output = executor(decision=dict(decision), context=dict(context or {}))
    if not isinstance(output, Mapping) or not isinstance(output.get("status"), str):
        raise TypeError("executor must return a mapping with a string status")
    status = output["status"]
    if status not in SUPPORTED_STATUSES:
        raise ValueError(f"unsupported executor status: {status}")
    event = {"action": action, "status": status,
             "output_summary": str(output.get("summary", "")),
             "evidence_ids": list(output.get("evidence_ids", [])),
             "state_updated": False}
    if hasattr(state, "_change"):
        state._change("action_execution", [action], event)
    if hasattr(cycle, "record"):
        cycle.record("action_execution", status, str(output.get("summary", "")))
    result_status = "paused_for_human" if status == "needs_human_review" else status
    return ExecutionResult(result_status, action, dict(output), str(output.get("summary", "")), [event])
