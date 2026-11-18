# Cycle 125 — Verified consistent database checkpoints

## Starting point

Continues verified Cycle 124 archive SHA-256
`f0f6a3bbe521888885dbd965f1c1eb00d6a2b27fb3d1af925715ec7748f6a018`.
The unchanged baseline passed **465 tests in 5.43s** before implementation.

## Behavior

Adds dd_research_runtime.checkpoints with three explicit library APIs:

- `create_checkpoint(store, destination)` uses SQLite's backup API against a pinned
  read snapshot, not a raw copy of the live .db file. It normalizes only the staged
  copy to a standalone database and validates it before publishing a ZIP.
- `inspect_checkpoint(checkpoint_path)` verifies the archive, database hash, SQLite
  integrity/foreign keys, supported schema, full persistent ingestion/review history
  and, when present, the complete queue/termination/renewal history. It returns the
  manifest without publishing a database or running migrations/repair.
- `restore_checkpoint(checkpoint_path, destination)` performs the same checks and
  publishes the verified standalone SQLite database at a new path. Applications can
  then open it through PersistentEvidenceStore and PendingRetrievalQueue as appropriate.

The checkpoint contains exactly research.sqlite and manifest.json. The manifest has
format/version, database SHA-256 and verified counts: state/ledger revisions, operations,
legacy/retained review coverage, retained snapshot sets, effective candidate lifecycle
counts and supported tables. It contains no machine-specific source file path.

All research state, human gates, audit receipts, legacy coverage, full review archives,
retained source snapshots and optional pending/committed/rejected/cancelled/superseded
candidates are copied together. Inspection validates the copied database directly using
read helpers; it does not invoke constructors that might recreate missing schema.
No external action, source retrieval or gate approval is performed during restore.

## Consistency and publication

The source read transaction pins a consistent SQLite snapshot while backup runs.
A concurrent WAL writer may commit new data, but the checkpoint remains one complete
revision. The source is not mutated, migrated or repaired by checkpoint creation.
Normal rollback-journal read locking may delay writers during the copy.

Creation and restore stage files privately, verify them, fsync the file and publish
through an exclusive hard link in the destination directory. Existing paths, including
symlinks, are never overwritten. Publication is atomic on the tested local filesystem;
file permissions are set to owner read/write (0600). There is no replacement fallback
on a filesystem that cannot support the hard-link operation.

Before-publication failure leaves no destination. A process crash or exception after
publication can leave a complete valid destination even if the caller saw no result.
Inspect that existing artifact rather than deleting or overwriting it on retry. This
is non-overwriting publication, not an idempotent job system or power-loss guarantee.

## Archive bounds and input handling

Restoration accepts exactly two fixed member names, rejects duplicate/unexpected
members, encryption and unsupported compression, and streams members to private
staging paths without extracting archive-supplied paths. It bounds the database at
256 MiB, the manifest at 64 KiB, and the outer archive with overhead allowance.
Creation enforces the same database/manifest size policies.

Manifest keys must be unique; version and verified summary types must match exactly.
A matching file hash alone is insufficient: altered receipt/history data still fails
semantic validation. Unsupported tables, triggers/views and incomplete queue schemas
are rejected rather than silently omitted or repaired. Legacy review gaps remain gaps.

## Verification

See TEST_RESULTS.md. Added tests cover state/gates/snapshot roundtrip; all candidate
lifecycles and renewal lineage; a WAL commit during backup; non-overwrite behavior;
failures and actual process death before/after publication; concurrent publication;
corrupt hashes/databases/history; duplicate members/manifest keys; traversal-shaped
members; mismatched summary types; size limits; schema loss; legacy coverage; and
owner-only published file modes. All prior recovery, ingestion and gate suites remain.

## Limits and next work

- Checkpoint ZIPs and staging databases contain plaintext research data and full retained
  source text. Owner-only file mode is not encryption. Host storage, backup destinations,
  encryption and access controls remain host responsibilities.
- Abrupt process death can leave private staging directories containing plaintext files.
  Normal exceptions clean staging. There is no automatic orphan cleanup, retention
  policy, scheduled backup, remote upload or checkpoint catalog in this cycle.
- SHA-256/manifest checks detect partial corruption, not authenticity or coordinated
  rewriting. A fully rewritten internally consistent database is not externally anchored.
  Host reviewer identity and source authenticity are not established by restoration.
- Only the current recognized runtime schema is supported. Older databases should first
  be explicitly adopted by the current store APIs; unknown future schema and custom
  tables are rejected. Oversized/invalid pending candidates may fail queue validation;
  checkpointing does not bypass current verification or repair source records.
- SQLite backup/read locks and local exclusive hard links were tested on macOS. File
  fsync is used, but there is no directory fsync protocol or verified hardware power-loss,
  disk-failure, network-filesystem, throughput or other-platform guarantee.
- The snapshot covers this SQLite database only, not external executors, files or source
  services. Retrieval-before-save recovery, exactly-once external work, scheduling and
  general durable claim/gate editing remain outside this cycle.
