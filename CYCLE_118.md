# Cycle 118 — Durable pending retrieval review

## Starting point

Continues Cycle 117 archive SHA-256
`412704375e678fe541ea2c92276ad88b19cec308696fb2930777beb95c69b8c8`.
The unchanged baseline passed **232 tests in 1.74s** before this cycle.

## Behavior

Adds `PendingRetrievalQueue(store)` in `dd_research_runtime.pending_retrieval`.
It creates an additive `pending_retrievals` table in the same SQLite database.
Existing state, receipt and operation data are preserved; no reinitialization is required.

- `save(candidate_id, candidate)` accepts a successful, structurally valid Cycle 117
  PersistentControllerStep, revalidates its executor output, and saves normalized
  retrieval documents plus the original state/ledger revisions. It returns a
  SavedRetrieval. Repeating an identical save is idempotent; changing content under
  the same ID fails. Save never creates evidence or an audit approval receipt.
- `load(candidate_id)` restores the review handoff after restart. `list_pending()`
  returns pending candidates in candidate-ID order. These methods reconcile the
  persistent ingestion history and all queue records before returning data.
- The host independently obtains source snapshots and creates an EvidenceReview
  with `review_retrieval(saved.validation, snapshots=..., reviewer=...,
  decision=..., rationale=...)`. Executor text must not substitute for independent
  source verification; tests use explicit fixtures only.
- `commit(candidate_id, review, authorize=...)` requires authenticated host approval
  and invokes existing durable ingestion. The queue uses the reserved operation ID
  `pending/<candidate_id>`; callers must not allocate that namespace for other writes.

The approved commit writes evidence, state, audit receipt, operation result and
candidate completion in the same BEGIN IMMEDIATE transaction. Before commit, it
checks saved payload integrity and request/revision equality. Completion verifies
its operation's receipt batch and state/ledger revision linkage. A failed or stale
commit leaves the candidate pending. It never refreshes revisions, approves human
gates, repairs a candidate, or promotes synthetic evidence to a real source.

Queue payloads have SHA-256 checksums; lifecycle checks reject false completion,
missing operation links and pending records whose reserved operation already exists.
Committed links are checked against stored operation results and receipt batch digests.

## Recovery and retries

The host must call save explicitly after preparation. Once save returns, reopening the
queue restores the candidate without re-executing retrieval. An identical save cannot
reset a completed record. A crash during approved ingestion rolls back candidate
completion together with evidence and receipts; after-commit crashes leave all
records committed. Retrying uses the same operation ID and requires current
reviewer authorization, without repeating retrieval or evidence ingestion.

Two commits for one candidate return one recorded result. Two different candidates
prepared against the same revisions compete: one may commit, while the other remains
pending and reports a stale revision. Committed retry results retain their original
revisions even after later unrelated ingestions.

## Verification

See TEST_RESULTS.md. Added coverage includes save/reopen/review/commit/retry, immutable
IDs, concurrent commits, competing candidates, stale state/ledger, authentication,
rejected/altered/wrong-batch reviews, synthetic/gate preservation, malformed/non-JSON
payloads, queue/operation integrity, legacy database adoption and actual process death
before and after ingestion commit. All previous crash/recovery/concurrency suites run.

## Limits and next work

- Saving is explicit, separate from external retrieval. A crash after retrieval but
  before save can still lose the candidate. External execution is not exactly once;
  the queue never executes or retries retrieval. It is a durable review handoff,
  not a worker scheduler, leasing system or complete job runtime.
- Only normalized documents and original revisions are stored. Controller decisions,
  cycle logs, executor summaries, source snapshot full text and pending reviewer
  drafts are not persisted. Pending review must be performed or repeated by the host.
- Queue load/list/save validate queue history; ordinary PersistentEvidenceStore.load
  continues to validate base ingestion history only. Do not use it as a substitute
  for queue validation. The private _pending_id ingestion parameter is queue plumbing,
  not a public independent approval API.
- Checksums and linkage detect partial corruption, not coordinated database rewriting.
  There is no signature, external anchor, tamper-proof deletion detection, or proof
  that a pending document really came from an external executor.
- Candidates are stored as plaintext source passages and metadata in the database.
  Host access controls, encryption/backup policy and retention remain host concerns.
  No cancellation, rejection lifecycle, cleanup, reassignment or revision-rebase API
  is provided. Rejected/stale candidates remain pending; they are never auto-approved.
- Queue and history verification scan stored records; there is no large-history
  scalability claim. SQLite's five-second lock timeout remains. There is no hardware
  power-loss, disk-failure, network-filesystem or other-platform validation.
- Durable claim/gate editing APIs remain future work. Identity authentication, source
  authenticity and independently obtained snapshots remain host responsibilities.
