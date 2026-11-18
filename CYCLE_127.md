# Cycle 127 — Bounded MVP contract, runnable fixture and gate scope fix

## Starting point

Continues verified Cycle 126 archive SHA-256
`adf0bb85d1bd28219a33a87049c82e9a07722dce602663e6bc30f6f1ab564cf9`.
The unchanged baseline passed **520 tests in 7.52s** before implementation.

## Delivered

MVP_ACCEPTANCE.json and MVP_BACKLOG.md establish eight required acceptance criteria,
code-grounded gaps, a finite target sequence for Cycles 128–131, deferred features and
a scope-change rule. This replaces open-ended incremental improvements with a working
local-MVP definition. It is a target, not a promise that four cycles can resolve all
future defects or obtain host acceptance automatically.

The new mvp_demo module runs a self-contained synthetic persistence vertical slice
through controller preparation, saved review/reopen, explicit host-callback permission,
reviewed atomic ingestion, full review/snapshot retention, idempotent retry, unapproved
publication blocking and checkpoint restoration. It records observed checks and gaps;
its exit code describes fixture success, while mvp_ready remains false.

A real gate defect found during the audit is fixed: ResearchState.execute_gated now
requires gate_type to match the requested gated action. A wrong-type or missing-type
approved gate cannot authorize or consume an unrelated action. Matching gates keep
their one-time execution behavior. The low-level approve_gate still does not provide
host authentication or durable gate storage; MVP-03 remains incomplete.

## Findings and stopping point

The main missing capabilities are durable analysis changes, durable authenticated gate
decisions, the full bounded workflow, a traceable report, and a host-checked acceptance
case. Read isolation correctly keeps local claim/gate edits out of the database; there
is no general state-update persistence API yet. The ingestion-only revision invariant
must be evolved safely before adding other state mutations.

Three criteria are fixture-verified, four are implementation gaps and one requires
manual/host acceptance. Those are statuses, not a percentage-complete estimate. The
fixture is neither a real study nor evidence that a human reviewer was authenticated.
All its source records are explicitly synthetic; no live-source framework or behavioural
economics framework is invented or inferred.

## Verification and limits

See TEST_RESULTS.md. Added tests exercise temporary/kept demo runs, actual module
subprocess execution, non-overwrite behavior, restored snapshots, explicit gap reporting,
contract/backlog consistency, missing fixture authorization, wrong-type and missing-type
gates, matching approvals and one-time execution. All earlier regression suites run.

The contract's implementation-gap statuses come from the code audit, not an automated
proof of all future feature absence. Fixture checks cover the implemented path only.
No durable claim/gate APIs, full research report, live-source acceptance case or real
identity-provider integration were implemented in this cycle. The gate-type tightening
can reject legacy approvals whose gate_type does not match; it never silently repairs
or broadens an approval. Plaintext storage, host source/identity responsibilities and
prior checkpoint/resource limitations remain.
