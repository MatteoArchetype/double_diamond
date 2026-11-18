# Cycle 119 — Explicit candidate rejection and cancellation

## Starting point

Continues Cycle 118 archive SHA-256
`b4e8791df8b7f9674336e34a2889d2a855ddc16a1fb87c9a65920b0b1542c9f7`.
The unchanged baseline passed **271 tests in 2.88s** before this work.

## Behavior

Adds two terminal actions to PendingRetrievalQueue:

- `reject(candidate_id, review, expected_ledger_revision=..., authorize=...)`
  requires an EvidenceReview with decision `rejected`, valid record digest and
  matching saved batch. The host authorization callback must return exactly True
  for `(review.reviewer, 'evidence_review')`. The rejection receipt and terminal
  decision are written in one BEGIN IMMEDIATE transaction. A new rejection uses
  the supplied current ledger revision; it does not use or silently refresh the
  candidate's older preparation revision.
- `cancel(candidate_id, actor=..., rationale=..., authorize=...)` requires a nonblank
  actor and rationale and exactly True authorization for `(actor, 'evidence_cancel')`.
  This is an administrative decision recorded in the terminal table. It creates no
  approval or rejection receipt and does not claim source review occurred.

The host's `evidence_ingest` permission alone does not grant either permission.
Every retry requires current authorization. Identical terminal requests return the
recorded result without another receipt; conflicting decisions fail. Committed
candidates cannot be rejected or cancelled. Rejected/cancelled candidates cannot be
committed, reopened, overwritten or reset by repeating save. Terminal operations
never mutate evidence, research state, gate status or the immutable candidate payload.

`load` returns effective status `pending`, `committed`, `rejected` or `cancelled`.
SavedRetrieval adds optional `termination` details: actor, rationale, kind, payload
binding and, for rejection, the full review and receipt linkage. `list_pending`
excludes all terminal records; known candidate IDs remain accessible through load.

## Storage, checks and compatibility

An additive `retrieval_terminations` table stores one checksummed decision per
candidate, bound to its existing payload digest. The Cycle 118 pending_retrievals
schema and its stored status constraint are unchanged: effective rejection and
cancellation overlay the immutable pending record. Existing pending/committed data
and operation IDs remain valid without reinitialization.

Queue verification checks terminal payload checksums, actor/rationale, lifecycle,
candidate binding, rejected review integrity and matching rejected receipt fields.
It rejects orphan terminal rows and terminal/committed contradictions. The pending
commit check runs under the ingestion write lock, so an approval cannot race past
a concurrent terminal decision. SQLite serialization selects one valid outcome.

## Recovery and concurrency

Before a rejection commit, failure rolls back both the receipt and terminal record.
After commit, reopening restores rejection and identical retry returns it without
another receipt. Cancellation is a single terminal write under the same transaction
pattern. Exception/KeyboardInterrupt fault tests cover both paths; spawned-process
termination tests cover rejection before and after commit. Concurrent identical
rejections produce one receipt. Races against approval have one successful outcome.

A rejection receipt advances the shared ledger revision and can therefore make other
prepared candidates stale. This is intentional optimistic concurrency; the queue
never silently rebases another candidate's approval context.

## Verification

See TEST_RESULTS.md. All previous ingestion atomicity, recovery, history integrity,
controller, queue, source, authorization, synthetic distinction and human-gate tests
remain included. New tests cover terminal lifecycle/restart/retry, separate permissions,
review/batch integrity, stale ledger revisions, conflicting decisions, corruption,
orphan rows, additive-schema adoption and approval races.

## Limits and next work

- Rejection still depends on host authentication and independently obtained source
  snapshots. A review digest is not an identity credential or source-authenticity proof.
- Terminal decisions are checksummed, not signed, externally anchored or protected
  from coordinated database rewriting. Deleting a cancellation record, or deleting
  both a rejection record and its receipt coherently, is not provably detectable.
  Queue verification does not replace base research-history verification, or vice versa.
- Cancellation has its own terminal audit record, not a ReviewLedger receipt. This cycle
  does not introduce a general action audit ledger, timestamps for terminal decisions,
  reviewer assignment, retention/deletion, reactivation, or stale-candidate rebasing.
- A rejected review already separately recorded in ReviewLedger cannot be silently
  attached: the existing unique-review constraint raises and rolls back the new
  terminal write. Hosts should use queue.reject for the atomic transition.
- Queue adoption is explicit. Legacy direct review/ingestion APIs do not automatically
  create or terminate queue records. The internal _pending_id parameter remains
  transaction plumbing, not an independent authorization surface.
- The gap between external retrieval and explicit save remains. External retrieval is
  not exactly once, and no worker leases/scheduler were added. Saved passages remain
  plaintext subject to host access, backup and encryption policies.
- Full-history scans and five-second lock timeout remain. No performance benchmark,
  hardware power-loss, disk-failure, live-source, real identity-provider or other-platform
  verification was performed. Durable claim/gate editing remains future work.
