# Cycle 126 — Checkpoint command-line workflow

## Starting point

Continues verified Cycle 125 archive SHA-256
`6cdfb5efc9b02ce89a0f4e0089f3b2ff94b1696e004851ca96b1e24cf7b75a06`.
The unchanged baseline passed **494 tests in 5.60s** before implementation.

## Behavior

Adds the standard-library entry point:

`python -m dd_research_runtime.checkpoint_cli {create,inspect,restore,verify}`.

Create accepts an existing database path and a new ZIP path. Inspect verifies a
checkpoint and reports its manifest. Restore verifies and publishes to a new database
path. Verify checks an existing database's supported schema and full state/review/
queue/renewal history without creating an archive or altering application data.

The new library helpers create_checkpoint_from_path and verify_database bind source
paths through SQLite mode=ro and query_only connections. They do not run store
constructors, create a missing database, adopt an old schema, initialize state,
recreate missing tables or repair corruption. The source remains unchanged. SQLite
WAL/shared-memory bookkeeping can still depend on filesystem permissions and SQLite's
own sidecar behavior; read-only application access is not a promise of zero sidecar I/O.

The commands delegate to Cycle 125's consistent backup, complete archive/database
validation and non-overwriting publication. Existing destinations are never replaced;
there is deliberately no force option. Human gate states, synthetic distinctions,
audit history, pending review status and explicit legacy gaps remain preserved.

## Reporting and errors

Success is JSON on stdout with command and verified manifest/summary. --pretty only
indents that JSON. No source passages, review bodies or rationale are printed by
successful summary commands. Error details are JSON on stderr, without application
tracebacks for handled validation, SQLite, filesystem and interruption failures.
Errors may include paths and integrity details; this is not an anonymization boundary.

Exit codes are 0 success, 1 operational failure, 2 usage error and 130 caught interrupt.
Structured error categories include usage, destination_exists, not_found, invalid_data,
permission_denied, io_error and interrupted. Standard help remains human-readable text
and requires no source database. SQLite permission/access errors can be categorized as
invalid_data when SQLite does not expose them as an OS PermissionError.

A post-publication interruption or output failure may leave a complete artifact.
The command does not delete or replace it automatically. Inspect an existing artifact
before retrying. Neither reporting nor CLI exit status changes the underlying atomic
publication guarantee or provides exactly-once job execution.

## Verification

See TEST_RESULTS.md. New tests invoke the actual module in separate processes for
create/inspect/restore/verify, confirm source bytes are unchanged, inspect restored
snapshots, exercise paths with spaces/URI-special characters, reject corruption and
pre-adoption/incomplete schemas without repair, check missing paths/non-overwrite,
and verify help, usage, error categories, interrupt handling and read-only SQL access.
All prior checkpoint, process-crash, concurrency, review, gate and recovery suites run.
CHECKPOINT_GUIDE.md provides a short user workflow and distinguishes source-cycle ZIPs
from database checkpoint ZIPs.

## Limits and next work

- These are explicit local commands, not a graphical app, scheduled backup service,
  migration tool, source collector or complete research workflow interface.
- Export/inspection relies on host filesystem access controls. It does not require or
  grant evidence-review permissions; it does not approve research or execute gates.
- Plaintext checkpoint/staging content, local hard-link publication, recognized schema,
  256 MiB database limit and 64 KiB manifest limit remain as documented in Cycle 125.
  No encryption, signatures, external audit anchor, remote upload or orphan cleanup.
- This does not provide OS memory/time limits, directory-fsync power-loss guarantees,
  storage-failure recovery or other-platform validation. A failed output stream can
  prevent delivery of the result even after publication; inspect existing destinations.
- External retrieval-before-save recovery, exactly-once external work, scheduling and
  general durable claim/gate editing remain outside this cycle. No live identity-
  provider, source-authentication or throughput benchmark was added.
