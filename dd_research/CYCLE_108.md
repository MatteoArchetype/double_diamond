# Cycle 108 — Bounded controller boundary

## Added
- `research_controller.py` wraps the existing one-step decision function.
- Returns an explicit status: `decision_recorded`, `paused_for_human`, or `stopped`.
- Validates the declared step budget and action shape.

## Control boundary
- Executes at most one decision per invocation. The declared budget is a safety bound, not a claim that a multi-step autonomous loop is implemented.
- Does not execute retrieval or any other selected action.
- Does not treat a selected action as evidence or as a state update.
- A later multi-step controller needs an explicit executor, a state refresh after execution, and a gate check before each consequential transition.

## Validation
- Full test suite is run before packaging.
