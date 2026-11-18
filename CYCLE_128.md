# Cycle 128 — Durable advisory analysis and typed state journal

## Starting point

Continues verified Cycle 127 archive SHA-256
`161bb16b253ad8f44a0cbd533348aa1cbcff3730e7317045e3dfd42e13e59bd0`.
The unchanged baseline passed **533 tests in 7.56s** before implementation.

## Delivered analysis API

PersistentEvidenceStore.apply_analysis accepts 1–100 typed commands (maximum 2 MiB
canonical request), operation ID, actor, rationale, expected state revision and host
authorization. The callback must return exactly True for (actor, 'analysis_write').

Commands add/update advisory claims, record evidence assessments, add/update
contradictions, put uncertainty records and set non-gated claim dispositions. They
run sequentially on an isolated state and commit together. Evidence, source records,
human gates and global workflow/publication state cannot be patched through this API.
See ANALYSIS_GUIDE.md for command fields and examples.

Claims retain belief history on update without recursively embedding the prior history
inside each new previous-state entry (which would grow exponentially); causal/generalisation claims require evidence
or an explicit unresolved/hypothesis state. References and typed record fields are
checked. Assessments require all supported qualitative dimensions and remain advisory.
They retain exact claim/evidence digests; assessment_is_current detects when subsequent
changes make one stale. Contradiction resolution and closed uncertainty require a
basis. Origin/advisory labels are derived, preserving synthetic-only/mixed/non-synthetic
classification without asserting that non-synthetic sources are authentic.

Status/disposition cannot be smuggled through a generic claim patch. New claims must
start as advisory draft/unresolved/hypothesis records. Withdrawal, splitting, hypothesis
promotion and flagged foundational/consequential/human-review dispositions fail closed
until durable human decisions are implemented. Analysis permission is not approval for
those decisions or external actions. Hosts still identify content-sensitive risks.

## Typed revision/history foundation

The ingestion-only assumption that every state revision has an evidence receipt is
replaced by an additive state_journal_policy plus state_mutations journal. Existing
verified state becomes a locally checksummed adoption checkpoint. Existing ingestion
IDs, results, receipt revisions, review coverage and retries are not rewritten or
backfilled. Invalid legacy state fails validation before journal anchoring.

Every post-adoption ingestion or analysis increments state revision once and records
its kind, operation ID, request/result digests, UTC timestamp, before/after state hashes,
after-state snapshot and hash-chain linkage. Analysis stores its full actor/rationale/
command request. Ingestion journal entries reference existing retained ingestion
requests instead of duplicating full source snapshots. Change-log timestamps within
one new transaction share its recorded timestamp for deterministic replay.

Integrity reads verify legacy ingestion coverage and replay every post-adoption event
from the adoption checkpoint, comparing the exact resulting state with stored snapshots
and current state. Deleting entries, breaking chain/hash links, changing request/result
bindings or rewriting snapshots without matching the recorded commands fails closed.
Replay validates recorded data; it does not call or reauthenticate the host actor.

Analysis receipts are not evidence-review receipts. ReviewLedger advances only for
actual review receipt writes. Existing verify_integrity().operations and checkpoint
summary.operations remain ingestion counts; mutation_coverage reports journal ingestion/
analysis counts. load_analysis_operation reads the recorded analysis request/result,
timestamp and entry hash. An analysis operation ID cannot collide with ingestion or
use the queue-reserved pending/ namespace.

## Atomicity, retries and queue interactions

Analysis state, mutation entry, audit change log and result commit in one BEGIN
IMMEDIATE transaction. Failure/KeyboardInterrupt or process death before commit rolls
back all writes. After-commit retry with the same request returns the original result
without another mutation, still requiring current authorization. Changed request IDs
conflict; new requests with stale revisions fail without silent refresh.

Ingestion now journals its state mutation in the same existing transaction as evidence,
receipt, review archive and queue completion. Analysis and ingestion may interleave;
review-only receipts remain independent. A pending candidate prepared before analysis
becomes stale because state changed, even if no evidence receipt was added. Existing
renewal and committed-retry semantics remain intact.

## Checkpoints and compatibility

Checkpoint/CLI verification recognizes the complete new journal pair, rejects partial
schema loss and verifies replay. New checkpoint manifests include state_mutations
coverage. New journal-bearing checkpoints need this cycle or newer; older tools reject
the unknown schema instead of ignoring it. Current tools still inspect/restore genuine
pre-journal checkpoints without silently migrating them; opening the restored database
through the current store explicitly adopts it before new writes.

Included fixtures cover unchanged Cycle 115 histories and an actual checkpoint produced
by unchanged Cycle 127 APIs. Do not mix older writer versions with an adopted database: unjournalled writes fail
new integrity checks. All fixtures are local synthetic/example regression data,
not independently reviewed live research. Older cycle directories are not dependencies.

## MVP progress

MVP-02 is fixture verified for durable advisory analysis, with sensitive dispositions
still blocked pending MVP-03. The offline demo now retains claims, a current advisory
assessment, contradiction, uncertainty and qualified disposition across restart and
checkpoint restore. It records 14 implemented-path checks and mvp_ready=false.

Three further cycles remain targeted: durable authenticated gate decisions (129),
bounded workflow/report integration (130), and host-checked acceptance/release (131).
These are conditional targets, not guarantees. MVP_ACCEPTANCE.json, MVP_BACKLOG.md and
the updated demo guide preserve the finite scope and stopping rule.

## Limits

- Actor authentication is supplied by the host callback; journal data and local hashes
  are not signatures, immutable storage, reviewer identity proof or external anchoring.
  A coordinated rewrite of the checkpoint, journal and related records can defeat them.
- Legacy state is adopted as a verified local checkpoint, not reconstructed into a
  fictitious complete historical mutation log. Previous identity/source gaps remain.
- Analysis is advisory. There is no durable human gate proposal/decision API yet, no
  full integrated research workflow/report and no real-source acceptance case. Direct
  edits of loaded state remain detached. Risk classification remains a host concern.
- Full after-state snapshots and replay grow storage and verification cost with history.
  Data, actor/rationale, claims and audit snapshots are plaintext. No scaling or complete
  resource-isolation claim is made; SQLite's five-second lock timeout remains.
- No live source/authentication provider, external exactly-once action, scheduling,
  hardware power-loss, disk-failure or other-platform verification was added. Prior
  checkpoint, payload-limit and source-authenticity limitations continue to apply.
