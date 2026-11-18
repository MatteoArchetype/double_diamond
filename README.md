# Current release: Cycle 154 — initial Discover notes for real questions

The local interface can display a clearly separated, read-only Discover brief attached
to case metadata. This presents source observations, provisional interpretations and gaps
before human source intake or phase decisions. Normal research controls remain available.
No core source/ledger/gate/workflow semantics changed. See CYCLE_154.md.
Earlier release sections below are historical.

# Double Diamond Research Runtime v0.2 — Cycle 93

A small executable contract for a traceable research-agent state, orchestration layer, and evidence-ingestion boundary.

## Cycle 93: evidence adapters

Added `dd_research_runtime.adapters.evidence`:

- `RetrievedDocument` represents retrieval output without interpreting it.
- `EvidenceCandidate` represents a bounded extracted finding.
- `EvidenceAdapter` registers source provenance and ingests evidence into `ResearchState`.
- Real-world evidence requires a known source and exact location.
- Synthetic sources/evidence remain explicitly marked and cannot silently become real evidence.
- Evidence IDs can be generated from a deterministic fingerprint.
- Re-ingesting the same finding/location is idempotent.
- A source's synthetic status must match its evidence candidates.

The adapter does **not** browse, scrape, decide truth, infer causality, or select conclusions. Those remain separate responsibilities.

## What this is not

This is not a production RAG system, secure database, access-control system, browser research system, or autonomous primary-research system.

## Run

`python run_tests.py`

\n## Cycle 101: research pipeline boundary\n
Added `research_pipeline.py` as a thin composition boundary:

- retrieval output is converted to bounded evidence without interpretation;
- evidence assessment is delegated to the existing claim-specific assessment layer;
- claim disposition is delegated to the existing controlled disposition layer;
- synthetic provenance remains enforced at the retrieval boundary.

The pipeline is deliberately not a browser, RAG store, causal inference engine, or autonomous decision-maker.

## Cycle 102: state integration boundary

The pipeline now exposes explicit state-recording adapters for evidence,
assessment, and disposition artifacts. These adapters do not alter the
underlying reasoning objects and do not implement persistence, retrieval,
RAG, or autonomous action. Unsupported state APIs fail explicitly rather
than silently mutating unknown structures.

\n## Cycle 103: ResearchCycle and ResearchState lifecycle

Cycle 103 connects the pipeline to the runtime's actual `ResearchState` and
`ResearchCycle` contracts. Retrieved passages become invariant-checked
evidence records; non-synthetic evidence registers a source; cycle start,
completion, and human-gate pause are recorded; pipeline operations enter the
change log. Assessments remain evaluation artifacts rather than an invented
first-class state collection. No live retrieval, RAG store, persistence
service, or autonomous external action is introduced.

### Next-action lifecycle boundary

`dd_research.next_action_state` validates and records a bounded next-action decision. It does not execute the action. If a human gate is required, the decision must route to `request_human_input` and include a gate reason. State and cycle records are both supported so the decision remains auditable through the research lifecycle.


### Derived next-action policy

`dd_research.next_action_policy` derives a bounded next action from explicit
research-state signals. The policy prioritizes required human gates, then
material unresolved contradictions, then satisfied stopping conditions, then
evidence gaps, and otherwise synthesis. It records the decision but never
executes the selected action.

## Cycle 115: durable reviewed ingestion

Use `PersistentEvidenceStore` from `dd_research_runtime.persistent_ingestion` to
commit evidence, state, audit receipt and retry record together. Initialize one
ResearchState per database, then call `ingest` with authenticated host authorization,
a stable operation ID and expected state/ledger revisions. Recover with `load()` and
retry the same request with the same operation ID after uncertain completion.
See [CYCLE_115.md](CYCLE_115.md) for the API contract and limitations.

Run the complete suite with Python 3.10 or later:

```sh
python -m pip install -r requirements-test.txt
python run_tests.py
```

## Cycle 116: reconcile recovery history

`PersistentEvidenceStore.verify_integrity()` checks operation/state revision coverage,
receipt linkage, evidence equality and source metadata consistency. `load()` and
`ingest()` also run these checks and fail closed on discrepancies. Read-side verification
uses a consistent transaction snapshot. Valid Cycle 115 databases work without a schema
migration. See [CYCLE_116.md](CYCLE_116.md) for checks, compatibility and remaining limits.

## Cycle 117: connect the controller to reviewed durable ingestion

Use `run_persistent_controller_step` from `dd_research_runtime.persistent_controller`
to prepare a candidate against verified durable state. Independently review its source
snapshots with `review_retrieval`, then explicitly call `commit_controller_retrieval`
with a stable operation ID and host authorization. Preparation never ingests evidence;
stale revisions require host reconciliation. See [CYCLE_117.md](CYCLE_117.md) for the
API and the pending-review persistence and external-execution limitations.

## Cycle 118: persist the review handoff

`PendingRetrievalQueue(store)` from `dd_research_runtime.pending_retrieval` saves a
Cycle 117 candidate with `save(candidate_id, candidate)`. Reopen with `load` or
`list_pending`, independently review `saved.validation`, then call
`commit(candidate_id, review, authorize=...)`. Evidence ingestion and queue completion
commit atomically. A saved candidate is not human approval. The queue never executes
retrieval. See [CYCLE_118.md](CYCLE_118.md) for recovery behavior and limitations.

## Cycle 119: finish candidates without ingestion

`PendingRetrievalQueue.reject` atomically records an authenticated rejected review
and its audit receipt. `cancel` records an independently authorized administrative
cancellation and rationale. Both preserve the candidate and block later ingestion.
Their permissions are `evidence_review` and `evidence_cancel`; ingestion permission
alone is insufficient. See [CYCLE_119.md](CYCLE_119.md) for retry, concurrency,
compatibility and audit limitations.

## Cycle 120: renew a stale review handoff explicitly

`queue.renew(parent_id, child_id, actor=..., rationale=..., expected_state_revision=...,
expected_ledger_revision=..., authorize=...)` creates a new candidate at current
revisions and preserves the old one as superseded. The permission is `evidence_renew`.
Use `queue.review(child_id, snapshots=..., reviewer=..., decision=..., rationale=...)`
to bind a fresh review to that candidate before commit or rejection. Old approval
records cannot be replayed. See [CYCLE_120.md](CYCLE_120.md) for scope and limitations.

## Cycle 121: retain review details with committed evidence

New persistent ingestions retain the full approved review and normalized request
atomically with evidence and audit receipts. `store.load_review(operation_id)` reads
that record; `store.review_coverage()` distinguishes retained reviews from explicitly
unavailable legacy payloads. Missing new records block recovery instead of being
reconstructed. See [CYCLE_121.md](CYCLE_121.md) for adoption, verification and limitations.

## Cycle 122: optionally retain reviewed source text

Pass `source_snapshots={source_id: {'text': ..., 'location': ...}}` to the persistent
store, queue or controller commit alongside the explicit review and authorization.
Content must match the review's snapshot hashes and source passages. It commits
atomically; `load_source_snapshots` reads it and `snapshot_coverage` reports gaps.
Retained content does not prove independent acquisition or authenticity. See
[CYCLE_122.md](CYCLE_122.md) for the retry contract and limitations.

## Cycle 123: reject ambiguous retrieval inputs

Provider-neutral retrieval now requires correctly typed source fields, an actual
boolean synthetic flag, consistent reserved synthetic provenance and finite JSON
metadata. Invalid batches fail before review/ingestion; nested metadata is copied
without stringifying arbitrary objects. See [CYCLE_123.md](CYCLE_123.md) for the
intentional compatibility tightening and remaining limits.

## Cycle 124: explicit payload limits

New retrieval and source-review submissions have document-count, UTF-8 field/passage,
JSON metadata/batch and source-snapshot limits. Oversize inputs fail without truncation
or partial ingestion. Committed snapshot archives retain their original integrity
checks without retroactive size rejection. See [CYCLE_124.md](CYCLE_124.md) for exact
limits, queued-data compatibility and resource-control limitations.

## Cycle 125: verified database backup and restore

Use `create_checkpoint(store, new_zip_path)`, `inspect_checkpoint(zip_path)` and
`restore_checkpoint(zip_path, new_database_path)` from `dd_research_runtime.checkpoints`.
The backup captures one SQLite snapshot and verifies state, reviews, snapshots and
queue history before publication. Destinations are never overwritten; restored gates
and pending reviews retain their states. See [CYCLE_125.md](CYCLE_125.md) for the
plaintext-content, schema, crash-recovery and filesystem limitations.

## Cycle 126: run checkpoint tools from a terminal

`python -m dd_research_runtime.checkpoint_cli --help` exposes create, inspect, restore
and verify commands. Source databases are opened read-only without implicit migration;
outputs are structured summaries, and existing destinations are never overwritten.
See [CHECKPOINT_GUIDE.md](CHECKPOINT_GUIDE.md) for examples and [CYCLE_126.md](CYCLE_126.md)
for error handling, scope and limitations. The runtime commands need only Python's
standard library; pytest remains a test dependency.

## Cycle 127: a finite MVP target and runnable fixture

Run `python -m dd_research_runtime.mvp_demo` for an offline synthetic persistence
vertical slice and honest MVP gap report. It currently reports `mvp_ready: false`.
See [MVP_DEMO_GUIDE.md](MVP_DEMO_GUIDE.md), [MVP_BACKLOG.md](MVP_BACKLOG.md) and
[MVP_ACCEPTANCE.json](MVP_ACCEPTANCE.json) for usage, required completion criteria and
the four targeted remaining implementation cycles. Wrong-type human gates now block
unrelated gated actions; durable authenticated gate decisions remain future work.

## Cycle 128: persist advisory analysis

`PersistentEvidenceStore.apply_analysis` atomically records typed claims, assessments,
contradictions, uncertainties and non-gated dispositions with `analysis_write` host
authorization and revision/idempotency checks. A typed replay journal preserves existing
ingestion histories and supports analysis-aware checkpoints. See
[ANALYSIS_GUIDE.md](ANALYSIS_GUIDE.md) and [CYCLE_128.md](CYCLE_128.md).
The offline demo now persists advisory analysis but still reports MVP incomplete.
Three targeted cycles remain in [MVP_BACKLOG.md](MVP_BACKLOG.md).

Cycle 139: use the Backups section or Restore a backup for saved-work recovery. See [BACKUP_INTERFACE_GUIDE.md](BACKUP_INTERFACE_GUIDE.md) for limits and the separate-copy confirmation flow.

Cycle 140: Deliver accepts separate evaluations and explicit criterion links. See [DELIVER_EVALUATIONS_GUIDE.md](DELIVER_EVALUATIONS_GUIDE.md).

Cycle 141 closes the browser open-question entry gap. Questions and explicit interpretation links use atomic advisory transactions; Define selection, reframing review and final acceptance remain separate. See UNCERTAINTY_INTERFACE_GUIDE.md.

Cycle 142 closes the browser unresolved-disagreement entry and report-inspection gap. Distinct interpretations and source origins are preserved; resolution, research judgments and host acceptance are not inferred. See DISAGREEMENT_INTERFACE_GUIDE.md.

Cycle 143 closes the browser evidence-fit assessment gap. Ratings remain advisory, exact-version-bound and distinct from source intake, accepted claims, human gates and empirical validation. See EVIDENCE_FIT_INTERFACE_GUIDE.md.

Cycle 144 fixes shared Develop selections by giving each competing alternative explicit independent interpretation/passage links and structured drafts. Existing phase transactions and human gates are unchanged. See DEVELOP_ALTERNATIVES_GUIDE.md.

Cycle 145 closes advisory draft interpretation revision in the browser while retaining history and exact-context staleness. It does not expose claim decision changes or replace human phase/framing gates. See ADVISORY_REVISION_GUIDE.md.

## Find publications in Discover

Choose **Find and review sources** from an open Discover case. For the search and review workflow, see [Cycle 155](CYCLE_155.md).
