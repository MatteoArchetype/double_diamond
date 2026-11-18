# Cycle 107 — Bounded research-loop composition

## Added
- `dd_research/research_loop.py` exposes `run_research_loop_step`.
- Composes the state-derived next-action policy with existing lifecycle recording.
- Enforces a reason when a human gate is required.
- Records one next-action decision in the state change log and research-cycle events.

## Boundaries
- Does not retrieve sources, call a model, execute tools, or perform consequential actions.
- Does not bypass human gates.
- Reuses the existing deterministic priority policy rather than creating a second policy.
- The loop is one-step only; repeated iteration and stopping remain externally controlled.

## Validation
- Full test suite run before packaging; see release output for test count.
