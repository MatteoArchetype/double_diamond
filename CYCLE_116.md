# Cycle 116 — Recovery history reconciliation

## Starting point

Continues the Cycle 115 archive with SHA-256
`456f41a4fb4d0866099e4ba97bdb0c310472d2833a020a721e86947dce1e29e0`.
The unchanged Cycle 115 source passed **171 tests in 0.97s** before this work.

## Problem and behavior

Cycle 115 verified a state checksum, the receipt hash chain and the requested retry's
result checksum. Those independent checks could miss a deleted operation record, a
receipt/result mismatch, or a state snapshot inconsistent with its recorded ingestion.

Cycle 116 adds `PersistentEvidenceStore.verify_integrity()`, returning
`state_revision`, `ledger_revision` and `operations` after reconciliation. It raises
ValueError on inconsistency. `load()` and every new ingestion or committed retry now
perform the same complete check before returning state or writing data. Corruption
is reported without automatic repair, deletion or reviewer-approval inference.

The checks reconcile:

- All operation result checksums and operation IDs; request digest format.
- Exactly one operation for each state revision, starting at one.
- Each operation's review digest, ledger revision and entry hash with an approved receipt.
- Increasing ledger positions in state revision order; review-only receipts may create gaps.
- Nonempty operation evidence, unique evidence IDs across ingestions and exact equality
  with the persisted evidence records.
- Non-synthetic source provenance, independence cluster, URL, title, publisher and
  retrieval/publication timestamps with the operation evidence metadata.

`load()` and `verify_integrity()` use one explicit SQLite read transaction so ledger,
state and operation queries see a consistent database snapshot during concurrent writes.
Ingestion retains its existing BEGIN IMMEDIATE transaction and atomic commit behavior.
Existing human authorization, review integrity, exact location, duplicate prevention,
synthetic flags and human gate semantics remain unchanged.

## Compatibility and testing

No schema change or reinitialization is required for valid Cycle 115 databases. An SQL
fixture generated through the unchanged Cycle 115 API verifies opening an existing
committed database, retrying its original operation and adding another ingestion.
It contains example.org test evidence, not independently retrieved research material.

Added cases cover partial record loss, receipt mismatches, modified source/evidence
records despite recomputed checksums, malformed operation results, duplicate state
revisions, reversed ledger order, review-only receipts, bootstrap evidence, synthetic
evidence, existing-database compatibility, and WAL commits during consistent reads.
The full prior crash, concurrency, authorization and gate suites continue to run.
See TEST_RESULTS.md for exact results.

## Limits and next work

- This remains accidental/partial-corruption detection, not authenticated history.
  A database writer able to rewrite all linked records and hashes can defeat it.
- Cycle 115 did not persist full request payloads or a bootstrap checkpoint. The check
  validates request digest format, not its reconstruction. It cannot prove bootstrap
  evidence provenance, detect all added evidence masquerading as bootstrap content,
  or prove that every approved receipt was intended for ingestion. Review-only receipts
  remain valid. Full historical state/gate reconstruction is not available.
- New ingestions and reads reconcile the full operation history and load full result
  payloads. This favors integrity over throughput; no performance benchmark or large
  history scalability guarantee is provided. SQLite's five-second busy timeout remains.
- Corrupt databases require investigation; there is no automated repair. Missing legacy
  audit links are not backfilled or inferred from surviving evidence.
- Only PersistentEvidenceStore.ingest provides coordinated durable ingestion. Controller
  adoption and durable claim/gate update APIs remain future work. Returned states remain
  detached snapshots; modifying one does not persist changes.
- Reviewer identity/access and independently obtained source snapshots remain host
  responsibilities. No live-source verification, external anchoring, signatures,
  hardware power-loss testing or other-platform testing was added.
