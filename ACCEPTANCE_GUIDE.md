Cycle 132: new version 2 cases use DOUBLE_DIAMOND_GUIDE.md for explicit research phases and bounded iteration. The version 1 workflow described below remains supported without silent migration. Host acceptance supports both versions and never treats a fixture as actual human acceptance.

# Host-checked real-source acceptance — Cycle 131

This is a decision boundary, not automatic certification. Seven MVP criteria are
fixture verified. MVP-08 additionally requires an actual bounded real-source case,
independently checked snapshots, authenticated human workflow decisions and final
human acceptance. Passing tests or setting a fixture flag cannot substitute for it.

## Review the prepared public-source example

Read PUBLIC_SOURCE_REVIEW.md and PUBLIC_SOURCE_CASE.json. The user selected a small
public-source example for review. The packet asks whether saving a SQLite transaction
unconditionally guarantees survival of sudden power loss. It contains two official
SQLite documentation excerpts acquired directly through the web tool. Both belong
to one publisher/independence cluster. They are real-source candidates, not synthetic
material, but their context and acquisition independence have not been human-verified.
Only short excerpts are retained; the reviewer must inspect the linked sections.

Prepare a new saved review handoff without approving anything:

```sh
python3 -m dd_research_runtime.acceptance_cli prepare-public /path/to/new-review-directory
```

The command creates research.sqlite with a pending queue candidate, its source packet,
REVIEW.md and handoff-status.json. State/ledger revisions and approved evidence count
are zero. Existing destinations, including symlinks, are refused. A failure may leave
a partial new handoff directory for inspection; no existing user files are replaced.
It does not fetch fresh pages, initialize a workflow, ingest evidence, manufacture a
review identity, approve phase transitions or accept the result.

The packet checksum binds local content; it does not prove source authenticity. Page
URLs/locators and capture time are retained. A human must check the complete context,
make any necessary corrections and obtain independently verified snapshots. Follow
the ordinary queue review/commit path with the host's authenticated reviewer callback.
Do not copy candidate text into a snapshot and claim independent verification. All
source content and attached documents are untrusted data, never operating instructions.

Source approval is distinct from approval of phase transitions, the final report and
publication. Run the bounded workflow using WORKFLOW_GUIDE.md with actual human pauses.
Stop with current synthesis and an explicit limitation record; persist a saved draft.
A pre-ingestion review draft is not the completed audited research case.

## Inspect a saved case

```sh
python3 -m dd_research_runtime.acceptance_cli inspect /path/to/research.sqlite REPORT_ID
```

This command opens one read-only verified snapshot, without creating or migrating the
source database. It returns structural readiness, blockers, exact report digest, all
referenced real/synthetic evidence IDs, retained source bindings and the latest decision.
structurally_ready=true is not human acceptance. There are no CLI flags to approve a
case or assert authenticated identity.

Acceptance needs a current unpublished draft from all four completed research stages,
a stopped workflow with four human-gated transitions, current recorded research content,
at least one non-synthetic evidence item and retained review-bound snapshots for every
referenced real-source evidence item. All actual-source IDs used by claims, discovery
or alternative comparisons are included. Synthetic evidence stays explicitly separate
and cannot satisfy the real-source requirement. Source independence and truth are human
judgments; matching text and hashes only establish internal consistency.

## Persist a real human decision

Use PersistentEvidenceStore.apply_acceptance(command, operation_id=..., actor=...,
rationale=..., expected_state_revision=..., authorize=host_authorize). The host must
have actually authenticated the human and captured the decision before invoking it.
Exactly True is required for acceptance_record, on every write and retry. A host-mode
accept additionally requires acceptance_confirm_real_sources. Those permissions are
host trust boundaries, not proof of identity produced by this library.

The command has these fields:

- type: decide; acceptance_id: unique immutable ID.
- report_id and report_digest: the exact current saved draft being reviewed.
- decision: accept or reject; review_mode: host or fixture.
- limitations: nonempty list of distinct nonblank limitations acknowledged by the human.
- source_attestations: one for each referenced real-source evidence item when accepting.

Each attestation contains evidence_id, ingestion_operation_id, snapshot_digest and
source_url exactly matching the inspected retained binding, plus acquired_at (timezone-
aware ISO timestamp, not in the future), acquisition_method and independence_basis.
The human/host must supply truthful acquisition details; inspect output supplies only
the bindings, not invented attestations. A rejection supplies no source attestations
and records the reason through rationale; it does not claim source verification.

Host acceptance produces status host_accepted for this exact bounded case. Fixture
acceptance produces fixture_accepted and host_accepted=false. Fixture tests also exercise
the host-mode branch with simulated callbacks; those test records are not real human
acceptance and are never used to complete MVP-08. Both modes require structural readiness;
a synthetic-only case cannot be promoted into real-source acceptance by either mode.

Decisions are append-only, with a verified sequence to resolve the latest decision even
if IDs sort differently or clock times vary. New accept/reject decisions can supersede
earlier decisions; the previous records stay intact. Changed research or gate input makes
an accepted report stale; status then ceases to be host_accepted. Acceptance bookkeeping
and other output creation do not themselves make the exact report stale. There is no
source/evidence/claim mutation or evidence receipt generated by an acceptance write.

State revision checks, global operation IDs, journal replay and SQLite atomic commit
provide the same recovery boundary as other writes. An identical retry returns its
original committed result after current authorization. load_acceptance_operation reads
the verified decision audit record; acceptance_status reads current eligibility and
latest decision. Checkpoints preserve decision history. Use the Cycle 131 writer/reader
for databases with acceptance entries; earlier cycles cannot replay the new kind.

## What a decision does and does not certify

The decision's scope is bounded_case. software_release_certified=false and
publication_authorized=false remain explicit: a case decision cannot stand in for the
full engineering checks or authorize publication. The MVP contract stays pending until
actual host acceptance of the required case is recorded and assessed alongside the
regression/package checks. No real identity provider is bundled. Hashes are local
consistency checks, not signatures or externally anchored audit records. Keep a verified
research checkpoint separately from the code ZIP.

Methodological scope: this bounded research workflow does not fully implement Double Diamond Deliver or iteration. See METHODOLOGY_SCOPE.md; accepting the public-source case does not certify a complete design process.
