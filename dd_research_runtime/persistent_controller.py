"""Explicit controller -> candidate -> human review -> durable ingestion bridge.

Preparation never ingests evidence. Controller/executor callbacks run outside the
SQLite write lock on a detached state. Their external side effects are not covered
by the evidence transaction and are not retried by this module.
"""
import copy
from dataclasses import dataclass

from .controller_execution import IntegratedStepResult, run_controller_execution_step
from .retrieval_validation import RetrievalValidation, validate_execution_retrieval


@dataclass(frozen=True)
class PersistentControllerStep:
    status: str
    state_revision: int
    ledger_revision: int
    step: IntegratedStepResult
    validation: RetrievalValidation | None


def run_persistent_controller_step(store, cycle, *, step_fn, step_context,
                                   executors, execution_context=None, max_steps=5):
    """Select and execute at most once against a verified durable snapshot.

    Returns ready_for_review only for structurally valid successful retrieval.
    Even that status is not human approval or proof of source authenticity.
    Callers retain this candidate for independent review; it is not a durable
    pending-job queue. No executor output or local state mutation is persisted.
    """
    state, state_revision, ledger_revision = store.load_with_revisions()
    step = run_controller_execution_step(
        state, cycle, step_fn=step_fn, step_context=step_context,
        executors=executors, execution_context=execution_context, max_steps=max_steps)
    validation = None
    status = step.status
    execution = step.execution
    if execution is not None and execution.action == 'retrieve' and step.status == 'completed' and execution.status == 'completed':
        validation = validate_execution_retrieval(execution)
        status = validation.status
    # Freeze outputs from executor-owned mutable objects for the review handoff.
    return PersistentControllerStep(status, state_revision, ledger_revision,
                                    copy.deepcopy(step), copy.deepcopy(validation))


def commit_controller_retrieval(store, candidate, review, *, operation_id,
                                authorize=None, source_snapshots=None):
    """Explicit reviewed commit, with the revisions observed before execution.

    A stale candidate must be reconciled by the host; revisions are never silently
    refreshed. Committed retries still use the persistent store's idempotency key.
    Candidates are host data, not authenticated execution/reviewer credentials.
    """
    if not isinstance(candidate, PersistentControllerStep):
        raise TypeError('PersistentControllerStep required')
    candidate = copy.deepcopy(candidate)
    execution = candidate.step.execution
    if (candidate.status != 'ready_for_review' or candidate.validation is None
            or candidate.validation.status != 'ready_for_review'
            or candidate.step.status != 'completed' or execution is None
            or execution.action != 'retrieve' or execution.status != 'completed'):
        raise PermissionError('successful retrieval candidate required')
    # Revalidate the frozen executor output and require the reviewed candidate to
    # match it. Never trust a ready_for_review flag alone.
    validation = validate_execution_retrieval(execution)
    if validation != candidate.validation:
        raise ValueError('controller candidate does not match execution output')
    return store.ingest(validation, review, operation_id=operation_id,
                        expected_state_revision=candidate.state_revision,
                        expected_ledger_revision=candidate.ledger_revision,
                        authorize=authorize, source_snapshots=source_snapshots)
