# Cycle 115 — Coordinated persistent ingestion

## Verified starting point

Source archive: `double_diamond_research_runtime_v0_2_cycle114.zip`
SHA-256: `d80db2365138bf91ce385927f55b53e3372cf234707823eaf51026a986d29221`.
Extracted source passed the full pytest suite: **135 passed in 0.26s**.
The original `run_tests.py` reported 14/14; it only imported two test modules.
Cycle 115 replaces that runner with full pytest discovery and adds a test dependency file.
Archive contents are consistent with Cycle 114; no external signature or published
reference digest was supplied to independently authenticate the archive.

## Transaction boundary

`dd_research_runtime.persistent_ingestion.PersistentEvidenceStore` stores one research
state in the same database as `ReviewLedger`. `initialize(state)` explicitly bootstraps
a validated JSON-compatible ResearchState exactly once. `load()` returns an isolated
committed state and its state revision.

`ingest(validation, review, operation_id=..., expected_state_revision=...,
expected_ledger_revision=..., authorize=...)` takes a SQLite `BEGIN IMMEDIATE` lock,
checks the ledger hash chain and durable state checksum, checks revisions, stages the
existing `ingest_with_review` on the loaded state, then writes the audit receipt,
state snapshot and completed-operation result in one commit. The ledger's private
append helper uses the same connection and does not commit independently.
State and ledger revisions are separate because review-only receipts remain supported.

Use a stable, unique operation ID per intended ingestion and retain it across retries.
The operation ID is bound to the full review, batch payload and validation status.
Identical committed retries return the original result without another receipt or
state change, even after subsequent commits. Different requests reusing an ID fail.
Current host authorization is required for every retry. Expected revisions apply to
new operations; a completed retry returns historical revisions, so call `load()`
when current state is needed.

## Recovery and preserved controls

Pre-commit failures roll back all writes, including KeyboardInterrupt. After abrupt
process termination, SQLite recovers its uncommitted journal on reopening. A crash
after commit but before acknowledgement is resolved by the same operation ID.
No pending evidence is published in a separate mutable state. Connections close on
exit, and coordinated connections explicitly use synchronous=FULL and foreign keys.

Existing authorization, approval, review digest/batch binding, duplicate prevention,
source provenance and exact locator checks remain in use. Full snapshots preserve
human gate status; ingestion cannot approve or execute a gate. Synthetic evidence
retains its synthetic flag and provenance and does not gain a real source record.

## Verification

See TEST_RESULTS.md for the final full-suite result and packaged-source verification.
Added coverage includes exception and interrupt rollback at four boundaries; real
spawned-process termination before/after commit; lost acknowledgement; idempotency
and key collision; stale state and ledger revisions; receipt collision; partial batch
failure; independent connections and concurrent processes; authorization and review
failures; synthetic/gate preservation; checksums and bootstrap behavior.

## Limitations

- Only the new PersistentEvidenceStore.ingest path coordinates durable ingestion.
  Legacy ingest_with_review remains in-memory; separate append/ingest calls do not
  become atomic. Controller callers must explicitly adopt this API.
- The database is authoritative. Returned ResearchState instances are detached
  snapshots; edits to them are not persisted. This cycle provides no general-purpose
  transaction API for claim, gate or controller updates after initialization.
- One research state per database; snapshots must be JSON-compatible. Whole-state
  staging/serialization holds a single-writer lock. SQLite lock timeout is five
  seconds; callers handle contention and retry. No cross-database or external-service
  transaction guarantee is made. Operation records currently have no retention policy.
- Host authorization and independently obtained source snapshots remain caller
  responsibilities. Digests are not signatures, reviewer authentication, or proof of
  source authenticity. An attacker with database write access can rewrite checksums
  and chains; deletion/rewrite protection needs external anchoring and access controls.
- Crash tests cover process death on local SQLite storage, not power loss, disk failure,
  network filesystems, every SQLite journal mode, or every platform. Filesystem/hardware
  durability remains subject to SQLite and storage guarantees. No performance claim.
- Research-state checksums and ledger chain checks detect partial corruption, not an
  externally trusted complete history. Retry result checksums cover the requested
  operation, not a full independent reconciliation of every historical operation.
