# Cycle 120 — Explicit stale-candidate renewal

## Starting point

Continues the Cycle 119 baseline copied before this cycle, which passed
**312 tests in 3.31s** before implementation. Its verified archive SHA-256 is
`ce8166cdf8493339b7bc7f5e4ba35a2307242d8e330633c1966aaab15c0a6563`.

## Behavior

Adds `PendingRetrievalQueue.renew(parent_id, child_id, actor=..., rationale=...,
expected_state_revision=..., expected_ledger_revision=..., authorize=...)`.
The host must authorize `(actor, 'evidence_renew')` with exactly True. Renewal is a
separate capability from ingestion, rejection and cancellation.

Within one BEGIN IMMEDIATE transaction, renewal verifies base and queue history,
requires the parent to be pending and stale, compares both expected revisions with
current durable revisions, and saves a new candidate ID with the original normalized
documents and current revisions. It writes an immutable checksummed lineage record
binding both payload digests, IDs, actor, rationale and revisions. The original
payload is never edited. The parent becomes effectively `superseded` and exposes
`successor_id`; the child is pending and exposes `renewal` metadata and `review_context`.

Each parent has at most one successor. Child IDs cannot replace existing candidates.
Lineage integrity checks reject missing records, changed payload bindings, invalid
revision progression, parent terminal-state conflicts and cycles. Superseded parents
cannot be committed, cancelled, rejected or renewed again. The new child may later
be reviewed, committed, rejected, cancelled or explicitly renewed if it becomes stale.

An identical renewal retry requires current authorization and returns its recorded
child even after later commits. Conflicting retries fail. Before-commit interruption
rolls back child and lineage together; after-commit recovery returns both. Competing
renewals or renewal/cancellation serialize under the database write lock.

## Fresh review binding

A batch-only review would otherwise be reusable because renewal preserves passages.
Cycle 120 adds a backward-compatible ContextEvidenceReview subclass and optional
`candidate_context` to `review_retrieval`. Ordinary reviews keep the original fields,
digests and retry serialization. A context-bound review includes its context in the
review digest and request digest.

`queue.review(candidate_id, snapshots=..., reviewer=..., decision=..., rationale=...)`
creates a review using explicit host-supplied independent snapshots and the saved
context. It never chooses approval automatically. Hosts may equivalently call
`review_retrieval(..., candidate_context=saved.review_context)`.

Approved ingestion and rejection of a renewed candidate require the matching context.
Old approvals, batch-only reviews and reviews from earlier renewal generations fail.
The commit-time check is repeated under the ingestion transaction lock. Ingestion
still requires its separate authenticated host permission and all existing source,
locator, digest, duplicate, synthetic and human-gate checks.

The review context prevents record replay; it does not prove a person actually
re-read the material, independently retrieved snapshots, or used a trusted identity.
Those remain host responsibilities. No external retrieval is performed by renewal.

## Compatibility and verification

An additive candidate_renewals table preserves earlier state, queue, terminal and
receipt schemas. Ordinary review records retain their prior digest representation;
all earlier compatibility fixtures and retry tests remain included. All source and
tests needed by this cycle are in its own directory; older cycle folders are not
runtime dependencies.

See TEST_RESULTS.md for exact results. New tests cover renewal/restart/fresh-review
commit; old approval/rejection blocking; multiple renewal contexts; state and ledger
staleness; authorization; immutable parent lifecycle; rollback/KeyboardInterrupt;
actual process death before and after commit; concurrent identical/different renewals;
renewal/cancellation races; payload/orphan corruption and source snapshot fidelity.

## Limits and next work

- Renewal preserves retrieved documents; it does not refresh source content or close
  the retrieval-before-save gap. Hosts decide whether material remains current and
  obtain independent snapshots for the new review.
- Renewals are checksummed lineage records, not ReviewLedger approval receipts or
  cryptographic attestations. Coordinated rewriting/deletion can defeat checks.
  Historical operation storage retains request digests, not full context-bound review
  payloads for independent reconstruction of every successful historical approval.
- A renewal context prevents replay of an old review record, not malicious host code
  forging a new record. Legacy direct ingestion remains a separate host-controlled API;
  only queue-based commit enforces queue lifecycle and renewal context.
- Only pending, stale candidates can renew. Rejected/cancelled candidates cannot be
  reactivated. No deletion, cleanup, assignment, scheduler, external execution retry
  or general durable claim/gate editing API is introduced.
- Queue verification scans history and lineage; no large-history performance claim.
  The existing five-second lock timeout remains. No live-source, identity-provider,
  hardware power-loss, disk-failure or other-platform validation was performed.
- Source passages remain plaintext subject to host access, encryption and backup
  controls. Base store reads do not substitute for queue/lineage verification.
