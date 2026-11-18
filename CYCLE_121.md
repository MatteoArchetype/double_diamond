# Cycle 121 — Retain complete approved review requests

## Starting point

Continues verified Cycle 120 archive SHA-256
`8a1460a4682bba34dd547d09a6ff5978355c961aca3966f0064a2602b2d83bdd`.
The unchanged baseline passed **350 tests in 5.11s** before implementation.

## Behavior

New persistent ingestions save their complete canonical request in an additive
`ingestion_review_archive` table: full EvidenceReview fields (including snapshot
digests and optional renewal candidate context), validation status and normalized
document payloads. The archive checksum must equal the existing operation request
digest. Evidence, state, receipt, operation result, retained request and optional
queue completion commit in the same SQLite transaction.

Before commit and on subsequent verified reads, reconciliation checks:

- Archive/request checksum equality and a complete approved review record.
- Recomputed review record digest and batch digest.
- Matching receipt batch, reviewer, decision and rationale.
- Snapshot digest count matching the document count; no approved duplicate keys.
- Retained documents normalized back to the exact committed evidence records.
- For new queue ingestions, the review context matches recorded renewal lineage.
- Required archive coverage after the adoption boundary, with no orphan records.

A corrupt or missing required archive record blocks load, integrity inspection,
new ingestion and committed retries. A retry never recreates missing review content
from caller claims. Existing authorization, human gates, source fidelity checks,
synthetic flags and queue lifecycle checks remain in place.

## Legacy adoption

First opening an older database installs both archive tables and a checksummed
`review_archive_policy` marker in one transaction. The marker records the existing
state revision as the legacy boundary. Earlier operations remain explicitly without
retained review payloads. No review details, source snapshots or approvals are
reconstructed, inferred or backfilled. New ingestions after the boundary require
archive records. Identical legacy retries remain legacy and do not add archives.

Schema parity and policy presence are checked on reopening: losing either archive
table or deleting an existing policy row is not silently treated as first adoption.
This is a local integrity check, not an externally authenticated migration marker.

New APIs:

- `store.review_coverage()` returns legacy operation count, retained-review count and
  legacy state revision after full history reconciliation.
- `store.load_review(operation_id)` returns an isolated retained request/review,
  raises LookupError for known legacy operations, and KeyError for unknown IDs.
  This read requires host-controlled database access, not a claimed reviewer identity.

## Recovery and compatibility

Before-commit failure or process death rolls back the archive with every other
operation record. After-commit recovery returns the retained record and identical
retry creates no additional row. Concurrent identical ingestions retain one review.
Queue archive failure leaves its candidate pending with no committed evidence.

Existing databases and ordinary review digests remain compatible. Tests include
an unchanged Cycle 115 database and a SQL fixture generated using unchanged Cycle 120
APIs with a committed renewal-context review. Its records stay legacy after adoption,
while later writes receive full coverage. All required fixtures are included locally;
older cycle folders are not needed to run this package.

## Verification

See TEST_RESULTS.md for exact results. Added coverage includes archive reads and
isolation, adoption/coverage, legacy retry, missing/altered/orphan records, policy and
schema loss, recomputation of review/batch digests, context/lineage mismatch, concurrent
writers, queue rollback, actual process death and no reconstruction from retry claims.

## Limits and next work

- Pre-adoption review bodies remain unavailable. The legacy boundary is locally
  checksummed, not signed or externally anchored; coordinated edits to policy,
  history and archives can defeat these checks.
- Retention applies to approved persistent ingestion requests. Direct ReviewLedger
  review-only receipts are not retroactively expanded. Queue rejection retains its
  review through the existing terminal record path, outside this archive API.
- Snapshot hashes are retained, not full independently obtained source snapshot text.
  A record's presence and internal consistency do not authenticate its reviewer,
  prove independent verification or establish source truth. Host identity/access
  controls and independent source acquisition remain necessary.
- Archive payloads include passages, metadata, reviewer names and rationale in plaintext.
  Host access, encryption, backup and retention policies remain host responsibilities.
- Full-history verification has additional read/serialization cost. No large-history
  throughput claim, hardware power-loss, disk-failure, network-filesystem or other-
  platform test was performed. Lock timeout remains five seconds.
- External retrieval-before-save recovery, worker scheduling, exactly-once external
  side effects and general durable claim/gate editing remain outside this cycle.
