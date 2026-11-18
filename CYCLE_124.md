# Cycle 124 — Bounded retrieval and snapshot submissions

## Starting point

Continues verified Cycle 123 archive SHA-256
`22ed2c197c6c820c19da210cdc3333b88c7ae71717f16d2c800cf19667523bf5`.
The unchanged baseline passed **449 tests in 5.17s** before implementation.

## Behavior

Adds explicit application policies in dd_research_runtime.payload_limits:

- Maximum 100 documents in a retrieval batch.
- Maximum 8 KiB UTF-8 per source field, including optional non-null fields.
- Maximum 64 KiB UTF-8 for an evidence passage.
- Maximum 64 KiB canonical JSON for each document's metadata.
- Maximum 2 MiB canonical JSON for the normalized document payload batch.
- Maximum 1 MiB combined UTF-8 text and locator per reviewed source snapshot;
  a locator also has the 8 KiB field limit.
- Maximum 8 MiB combined text/locator bytes across the reviewed source snapshots.

KiB and MiB use powers of 1024. JSON accounting uses sorted keys, compact separators,
UTF-8 and unescaped Unicode; JSON escaping still counts toward the byte limit. These
are fixed engineering policies, not externally established research standards.

Oversize inputs raise a clear error or produce an entirely rejected retrieval
validation with no documents. Nothing is truncated, silently trimmed, split, promoted
to evidence or auto-approved. Exact passage/location fidelity remains required.

Checks run in RetrievedDocument validation/conversion, structural retrieval validation,
explicit source review and direct persistent ingestion. A manually constructed
ready_for_review wrapper cannot bypass batch limits. Retained snapshots are checked
again before new ingestion commits. Existing authorization, review digest, synthetic
classification, human gates, duplicate checks and transaction rollback remain intact.

## Historical data and compatibility

The limits apply to new source-input submissions and review handoffs. Committed
snapshot archives remain subject to the original integrity/hash/passage checks but
are not retroactively rejected solely for exceeding a new input size policy. Historical
archive reading may therefore still load large content; the limits are not a cap on
total database history or process memory.

Previously saved queue candidates are revalidated as before; an oversized candidate
can fail closed on reading. Its bytes, digest and approvals are not rewritten or
repaired. Hosts must investigate and prepare a new bounded, faithful review handoff
explicitly. No stale revision, review or source content is silently changed.

All earlier valid examples and database fixtures continue to pass. No database schema
change or new authorization permission is introduced. Source bodies and total history
remain governed by the storage policies documented in earlier cycles.

## Verification

See TEST_RESULTS.md. Added coverage includes exact and over-limit document counts,
field/passages, Unicode byte measurement, canonical/escaped metadata size, total batch
size, all-or-nothing rejection, synthetic input parity, manual-wrapper bypass prevention,
direct-ingestion rollback, snapshot boundary/totals, pre-commit retention checks and
non-rewriting of historical archives/queued records. All prior crash, concurrency,
source, review, queue, renewal and gate tests remain included.

## Limits and next work

- These checks operate on already materialized Python inputs. They do not provide
  streaming HTTP download limits, executor timeouts, process isolation or an operating
  system memory budget. Python normalization, deep copies and JSON chunks can allocate
  memory before a size rejection. Arbitrary host callbacks remain trusted code.
- Only normalized source documents and reviewed snapshot text/locators are bounded
  here. Executor summaries, reviewer rationale, whole ResearchState snapshots, total
  database size, cumulative audit history and all other host data are not bounded.
- Archived history is intentionally not retroactively capped. Full-history verification
  still scans content and can grow in cost. No large-history performance claim or
  benchmark is provided. SQLite's five-second lock timeout remains.
- Size/shape checks do not establish source authenticity or independent acquisition.
  Human authorization and host-supplied independent snapshots remain required.
- External retrieval-before-save recovery, exactly-once external actions, scheduling
  and general durable claim/gate editing remain outside this cycle. No live-source,
  identity-provider, hardware power-loss, disk-failure or other-platform validation ran.
