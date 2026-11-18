# Cycle 122 — Optional retention of reviewed source snapshots

## Starting point

Continues verified Cycle 121 archive SHA-256
`9d2030ac23e04488e1b83d7708910f702272a31b45c64f3950311b0847e65e9d`.
The unchanged baseline passed **376 tests in 5.33s** before implementation.

## Behavior

Adds optional `source_snapshots` to PersistentEvidenceStore.ingest,
PendingRetrievalQueue.commit and commit_controller_retrieval. The caller supplies
exactly the snapshots used to create the explicit approved EvidenceReview:

`{source_id: {'text': full_source_text, 'location': exact_locator}}`.

Snapshot IDs must exactly match the batch. Each entry must contain only string text
and location. The evidence passage must occur verbatim in the text, its exact locator
must match, and the recomputed source ID/text/location hash must match the review's
snapshot digest in document order. Unexpected IDs/fields, mismatched full text,
passages or locations fail before mutation. Mapping order does not change document
order. Inputs are deep-copied with the review/batch for the handoff.

The verified snapshot mapping becomes an optional field in the canonical retained
request. It is covered by the operation request digest and review archive checksum,
and committed atomically with evidence, state, receipt, review record and queue
completion. No new table or migration marker is required. Recovery repeats the
passage/location/hash checks as part of full review archive reconciliation.

Supplying snapshots does not create approval, grant authorization, refresh stale
revisions, change human gates or promote synthetic content to a real source.
Snapshot content still must be independently obtained by the host; internally
consistent executor text is not proof of independent verification or source truth.

## Reads and coverage

- `store.load_source_snapshots(operation_id)` returns isolated retained text and
  locations. It raises LookupError when a known operation lacks retained snapshots
  (or its review is legacy) and KeyError for an unknown operation.
- `store.snapshot_coverage()` reports legacy operations, retained snapshot sets,
  retained reviews without full snapshots, and total snapshot entries across sets.
  These counts do not claim unique external sources or verified source authenticity.
- `store.load_review(operation_id)` also includes the optional source_snapshots field
  for operations that opted in. Earlier request/review representations stay unchanged.

A retry must preserve its retention choice and exact text/locations. An operation
originally committed without full snapshots cannot acquire them through retry, and
one committed with snapshots cannot silently omit them during retry. There is no
backfill or post-commit attachment API; retries never fabricate missing content.

## Recovery and compatibility

Before-commit failures and process death roll back snapshot content with the evidence
and audit records. After-commit recovery restores all records; identical retry adds
nothing. Queue failure still leaves its candidate pending. Legacy fixtures and all
previous ordinary/context-bound review digests and retries remain compatible.

No older cycle directory is required to run this package. Existing retained reviews
without full snapshots remain readable, with explicit coverage reporting.

## Verification

See TEST_RESULTS.md. Added tests cover full-text reopen/isolation, opt-out and legacy
gaps, malformed/unrelated snapshot input, full-text hash matching, multi-document
ordering and Unicode, stable retry identity, rollback boundaries, actual process
death, queue/controller bridges, renewal context, synthetic distinction, current
authorization and rechecking modified snapshots despite recomputed request checksums.
All prior atomicity, recovery, concurrency, history, gate and source tests remain.

## Limits and next work

- Retention is optional. Earlier reviews/operations cannot provide source text they
  never stored. Reviews without retained snapshots can only be checked against their
  recorded hashes and other audit fields, not reconstructed source content.
- Retained text/location is caller-supplied text, not a signed publisher capture,
  retrieval timestamp attestation, binary/PDF preservation or source authenticity
  proof. Hosts must obtain independent snapshots and authenticate reviewers.
- Full source text is stored in plaintext within the review archive. Storage volume,
  access, encryption, backups, lawful retention and eventual deletion are host concerns;
  this cycle adds no purge, redaction, retention policy or post-commit attachment API.
- Checksums detect partial corruption, not coordinated rewriting. Removing optional
  snapshot content and consistently rewriting the request/archive checksums can erase
  the retention choice without an external anchor. There is no cryptographic signature.
- Verification scans all retained content and history, with no large-source size limit
  or performance benchmark. SQLite's five-second lock timeout remains.
- External retrieval-before-save recovery, exactly-once external actions, scheduling
  and general durable claim/gate edits remain outside this cycle. No live-source,
  identity-provider, hardware power-loss, disk-failure or other-platform validation ran.
