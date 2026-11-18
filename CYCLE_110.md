# Cycle 110 — Bounded controller/executor integration

Adds `dd_research_runtime/controller_execution.py` with `run_controller_execution_step`.

- One policy-selected decision, at most one allow-listed execution per call.
- Human-gated and stop decisions never reach an executor.
- Failed, no-result, and human-review statuses are preserved.
- Executor outputs are *unverified candidate material*, not evidence records.
- Evidence ingestion, provenance checks, and state refresh remain explicit downstream operations.
- No live web access, autonomous multi-step agent, or consequential action is implemented.

Tests: `python -m pytest -q tests` from the project root.
