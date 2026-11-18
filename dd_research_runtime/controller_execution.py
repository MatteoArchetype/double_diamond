"""Single-step decision-to-execution integration with explicit trust boundaries."""
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from dd_research.research_controller import run_bounded_research_controller, ControllerResult
from dd_research_runtime.action_executor import execute_registered_action, ExecutionResult

@dataclass
class IntegratedStepResult:
    status: str
    controller: ControllerResult
    execution: ExecutionResult | None
    reason: str


def run_controller_execution_step(
    state: Any, cycle: Any, *, step_fn: Callable[..., dict[str, Any]],
    step_context: dict[str, Any], executors: Mapping[str, Callable[..., Any]],
    execution_context: Mapping[str, Any] | None = None, max_steps: int = 5,
) -> IntegratedStepResult:
    """Select once, execute once if permitted, and never ingest output as evidence.

    A caller must independently validate retrieved material and invoke the
    established evidence-ingestion pathway before it can affect research state.
    """
    controller = run_bounded_research_controller(
        state, cycle, step_fn=step_fn, step_context=step_context, max_steps=max_steps)
    decision = controller.steps[0]
    if controller.status == 'paused_for_human' or decision.get('gate_required'):
        return IntegratedStepResult('paused_for_human', controller, None,
                                    decision.get('gate_reason') or controller.reason)
    if controller.status == 'stopped':
        return IntegratedStepResult('stopped', controller, None, controller.reason)
    execution = execute_registered_action(
        state, cycle, decision, executors=executors, context=execution_context)
    return IntegratedStepResult(execution.status, controller, execution,
                                execution.reason or controller.reason)
