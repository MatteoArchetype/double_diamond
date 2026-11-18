Cycle 132: new version 2 cases use DOUBLE_DIAMOND_GUIDE.md for explicit research phases and bounded iteration. The version 1 workflow described below remains supported without silent migration. Host acceptance supports both versions and never treats a fixture as actual human acceptance.

# Bounded research workflow and draft reports — Cycle 130

Use Python 3.10+ from this cycle's source directory. The runtime uses the standard
library; the full test suite additionally needs requirements-test.txt. Run the
synthetic demonstration with:

```sh
python3 -m dd_research_runtime.mvp_demo --keep /path/to/new-fixture-directory
```

This writes fixture.sqlite, a verified checkpoint, a restored database, demo-report.json,
and research-draft.md / research-draft.json. All identities and evidence in this run
are simulated. The real-source acceptance criterion remains pending. The demo reuses
its already reviewed intake; the regression suite also runs a brief-first case where
reviewed intake happens during discovery. No live research or external publication runs.

## Host integration

Initialize one PersistentEvidenceStore with an empty brief/scope/questions, or open
an existing compatible database. apply_workflow(command, operation_id=..., actor=...,
rationale=..., expected_state_revision=..., authorize=host_authorize) requires exactly
True for host_authorize(actor, 'workflow_write'). The host supplies authenticated
actor identity and permissions; never use fixture allow-lists for real authentication.
All new operations compare the expected current state revision. Changed operation-ID
reuse fails; an identical retry returns its prior result after current authorization.
load_workflow_operation(operation_id) returns a verified request/result/audit hash.

A start command has type start, workflow_id, brief (text), scope (text), questions
(1–20 unique nonblank strings) and max_alternatives (2–20). It persists the brief,
scope and question IDs and begins the brief phase. One bounded workflow is supported
per database. Existing nonempty briefs require explicit host migration into a new
case; they are never silently overwritten.

The ordered phases are brief → discovery → definition → alternatives → synthesis.
Before each advance, call transition_action(state, to_phase) from workflow.py. Propose
and approve this exact action with the durable gate API (GATE_GUIDE.md). Then submit
{type: advance, to_phase: ..., gate_id: ...}. workflow_write authorizes the bounded
local stage update; the durable human approval is consumed in the same transaction.
It does not require a separate generic gate_execute write. Pending, rejected, reused,
wrong-type or changed-content approvals cannot advance the workflow. Any research
content change after proposal invalidates the old transition action; obtain a new
proposal/decision. Gate bookkeeping alone does not change the research-content digest.
Do not consume the transition using generic gate_execute first.

## Phase records

Use {type: record, phase: CURRENT_PHASE, record: RECORD}. Each phase can be recorded
once. A record references existing reviewed evidence and advisory analysis; use the
intake/analysis APIs to create those records. Each stage retains a content-version
binding. Gate approval allows progression; it does not establish a claim's truth.

- Discovery: evidence_ids (nonempty) and notes.
- Definition: problem, claim_ids (nonempty), uncertainty_ids.
- Alternatives: alternatives (2 to max_alternatives). Each entry has alternative_id,
  hypothesis, test, outcome (supported / unsupported / inconclusive), claim_ids
  (nonempty), evidence_ids and limitations. Supported/unsupported outcomes require
  evidence IDs. Outcomes are host-recorded assertions, not independently run or
  validated experiments. Synthetic evidence retains its label for every outcome.
- Synthesis: summary, claim_ids (nonempty) and limitations.

All text fields are nonblank; references and unique IDs are checked. Each request
is bounded to 2 MiB. There are no automatic stage loops, source fetching, test runners
or scope expansions. A correction requiring a new phase record needs a new bounded
case; there is no implicit rewrite of stage history.

Finish with {type: finish, outcome: stopped|escalated, reason: ...}. Stopped requires
a recorded, current synthesis. Escalation is allowed from any active phase and must
state the reason. A terminal workflow cannot resume or change stage records. Later
advisory analysis can still be saved, but existing reports become stale; a regenerated
report explicitly marks any stages whose research content has changed since recording.
Regeneration never silently revalidates the old synthesis.

## Saved reports and export

After stop/escalation, persist {type: report, report_id: ...}. Reports retain the
brief, questions, stage records and stopping reason; claims as advisory interpretations
or hypotheses; exact evidence passages/locations and source metadata; original synthetic
flags and derived origins; assessments with current/stale status; contradiction and
uncertainty records; gate statuses at generation; and explicit limitations.
Original structured records remain in the JSON report and database. No record is
converted from synthetic to real evidence. An approval is not independent verification.

Reports are drafts, with publication_authorized=false. Their content digest binds the
saved report; report_is_current(state, report_id) checks its research/gate input version.
The digest excludes other outputs and audit bookkeeping, allowing multiple draft
exports of one consistent state. Gate decisions after generation make the old report
stale; no export dynamically substitutes a later approval into an old report.

```sh
python3 -m dd_research_runtime.report_cli /path/research.sqlite REPORT_ID /path/new-draft.md
python3 -m dd_research_runtime.report_cli /path/research.sqlite REPORT_ID /path/new-draft.json --format json
```

The exporter verifies recorded state/history in one read-only SQLite snapshot. It does
not create missing databases, adopt old schemas, change source records or overwrite
existing destinations (including symlinks). Stale reports fail by default. --allow-stale
exports an explicitly marked stale draft; JSON exports include current_at_export and
export_state_revision. Markdown treats research-controlled content as escaped text.
Publication, external execution, source acquisition and identity integration belong
to the host; this command performs none of them. Use checkpoints for research data
backup. The source ZIP contains code and fixtures, not your working research database.

Use the Cycle 130 writer/reader for databases with workflow entries. Earlier cycles
cannot replay the new workflow journal kind; do not mix writer versions. Existing
validated older histories remain readable and checkpoint-compatible with this cycle.

Methodological scope: this bounded research workflow does not fully implement Double Diamond Deliver or iteration. See METHODOLOGY_SCOPE.md; accepting the public-source case does not certify a complete design process.
