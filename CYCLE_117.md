# Cycle 117 — Controller-to-durable-ingestion bridge

## Starting point

Continues Cycle 116 archive SHA-256
`cb1307846879540d25246757bdd0318a7884a0ed847e7c166626118706264a21`.
The unchanged Cycle 116 suite passed **202 tests in 1.48s** before this cycle.

## Behavior

Adds `dd_research_runtime.persistent_controller` with two explicitly separate steps:

1. `run_persistent_controller_step(store, cycle, step_fn=..., step_context=...,
   executors=..., execution_context=..., max_steps=5)` loads verified durable state
   and both revisions from one read transaction. It selects and executes at most
   one action through the existing controller boundary, outside the SQLite write
   lock. Successful retrieve output is structurally validated and copied into a
   `PersistentControllerStep` candidate with status `ready_for_review` or `rejected`.
   Other actions, human pauses, failures and stop decisions cannot become evidence.
2. The host independently obtains source snapshots and creates an `EvidenceReview`
   with `review_retrieval(candidate.validation, snapshots=..., reviewer=...,
   decision=..., rationale=...)`. Only an explicit
   `commit_controller_retrieval(store, candidate, review, operation_id=...,
   authorize=...)` invokes the persistent ingestion transaction. This revalidates
   the copied executor output, requires it to match the candidate validation and
   passes the originally observed revisions to `store.ingest`.

A ready candidate is neither human approval nor proof of source truth. The commit
still requires host reviewer authentication/authorization, approved review, matching
review/batch digests, duplicate checks and the complete persistent-history check.
Human gate status is preserved; this API never approves or executes a gate.
Synthetic evidence keeps its explicit flag/provenance and does not gain a real source.

Adds `PersistentEvidenceStore.load_with_revisions()` to return detached state, state
revision and ledger revision in one consistent snapshot. Separate reads would risk
binding the decision to revisions from different concurrent commits.

Controller and executor state mutations occur only on the detached snapshot. They
cannot sneak unreviewed evidence or gate approvals into the durable ingestion state.
Local controller/execution logs are not persisted by this bridge. The caller's cycle
object still receives the existing execution log events.

## Recovery and concurrency

The commit delegates to Cycle 115/116 atomic ingestion and history reconciliation.
An identical committed retry with the same operation ID returns its recorded result
without rerunning the executor or duplicating evidence. Current authorization is
required. If durable state or review ledger changes before an uncommitted candidate
is committed, its original revisions fail as stale. The bridge does not silently
refresh revisions or claim that a stale decision is still valid.

No schema migration is introduced. Legacy controller entry points remain available;
applications explicitly adopt the new persistent entry points.

## Verification

The suite covers the complete prepare/review/commit/reopen/retry flow; no automatic
ingestion; human gates and stop; failed/review-needed/no-result retrieval; non-retrieve
actions; malformed documents; executor failure; callback state isolation; source
snapshot mismatch; authorization/rejection/review tampering; candidate/output mismatch;
executor-output copying; stale state and ledger; synthetic evidence; corruption before
callbacks; no repeated external execution during commit retry; and consistent revision
capture during a concurrent WAL commit. Prior crash and concurrency suites remain.
See TEST_RESULTS.md for exact results.

## Limitations

- This is an opt-in bridge, not a durable work queue or complete autonomous controller.
  Candidates, execution output and pending human reviews are not stored in SQLite.
  The host must retain them across a process restart; this module provides no candidate
  serialization or job resumption API. A future cycle can persist that handoff.
- External executor side effects are outside the database transaction. Preparation is
  not exactly-once execution. Re-running preparation may repeat retrieval or other
  external work; commit retry alone does not rerun preparation. No automatic external
  retries are performed.
- Callbacks, candidates and authorization implementations are trusted host inputs,
  not signed execution attestations. Deep copying isolates subsequent object mutation,
  not arbitrary malicious Python callbacks or concurrent mutation during the callback.
- Rejected reviews are not automatically appended by this commit API. A host may record
  review-only receipts through ReviewLedger. No candidate is auto-approved or repaired.
- Durable claim/gate/controller-log update APIs remain unimplemented. Returned state
  edits are detached. Review authenticity, independent snapshots and source truth
  remain host responsibilities; tests use explicit fixtures, not real research evidence.
- Earlier history-check limitations remain: no signatures/external anchoring, full
  bootstrap reconstruction, protection from coordinated database rewriting, performance
  claim, hardware power-loss verification or cross-platform guarantee.
