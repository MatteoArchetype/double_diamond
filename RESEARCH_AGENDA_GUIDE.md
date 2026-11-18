# Turn evidence gaps into proposed research — Cycle 134

Double Diamond research should lead to the next useful question when the evidence
is insufficient. This release turns failed/unknown criteria into an inspectable
research agenda, anchored to the saved decision that exposed those gaps.

Each item states the gap, question, proposed method, return phase, priority and its
reason, effort, dependencies and what evidence would count as progress. Priorities
are recorded planning judgments, not automatic scores. A proposed order respects
prerequisites before priority. The agenda does not claim that an unanswered question
has been answered or that an item has been completed.

## Run the synthetic example

```sh
python3 -m dd_research_runtime.agenda_demo --keep /path/to/new-example-directory
```

The example first runs the criterion-linked learning loop, then proposes a contextual
observation and a dependent transfer test. It preserves synthetic/missing evidence
labels. The experiment item explicitly needs a separate primary-research approval.
No source retrieval, participant contact or experiment is performed by planning.
It writes research-agenda.md/json and an agenda checkpoint/restored database, alongside
the previous example's research draft. Existing directories are refused.

## Plan from a current decision

Use PersistentEvidenceStore.apply_workflow with type plan_research, agenda_id,
report_id, report_digest and items. Ordinary actor/rationale, global operation_id,
expected_state_revision and exact True workflow_write authorization apply.
The basis must be a current criterion-linked saved report. Agendas are immutable;
a revision needs a new ID and fresh current report. No historical report is rewritten.

There must be 1–20 items, covering every unmet criterion at least once. Multiple
items can address one criterion. An all-met report needs no artificial evidence gap,
so attempting to plan an unmet-criterion agenda from it fails. An item has:

- item_id and criterion_index: a unique item ID and the current unmet criterion index.
- evidence_gap and question: the missing evidence and what the research should answer.
- method: desk_review, interview, survey, experiment or analysis.
- target_phase: discover, define or develop; the phase to propose returning to.
- priority: high, medium or low, with a nonblank priority_rationale.
- success_signal: what new evidence would count as progress, without declaring success.
- effort: small, medium or large, a human planning estimate rather than a schedule.
- depends_on: distinct item IDs in this agenda. Self, unknown and cyclic dependencies
  fail. Sorting is deterministic by prerequisites, then stated priority and item ID.

The saved item retains the actual criterion text/outcome, prior next-research statement,
evidence IDs and origin from its basis report. It cannot target a met or nonexistent
criterion, silently substitute another report digest, or omit an evidence gap. Request
size remains bounded by the existing 2 MiB workflow-write limit.

## Planning and permission remain separate

Every agenda and item has status proposed and execution_authorized=false. Interview,
survey and experiment items display a primary_research gate requirement. This is a
hint about an existing human approval boundary, not an approval or execution token.
Other methods are also unexecuted proposals; an empty gate-hint list does not authorize
external retrieval or data access. Sensitive access, publication and consequential
external actions remain controlled by their existing host policies and exact gates.
There is no run, participant-contact, approval or scheduling command in the agenda CLI.

Use Double Diamond's existing approved revisit/reopen path when returning to research.
A materially changed frame still needs separate exact approval. Neither an agenda ID
nor a priority grants permission to change a question or perform primary research.
No dates, calendar appointments, reminders or automations are created by an effort estimate.

## Inspect and export

```sh
python3 -m dd_research_runtime.agenda_cli inspect /path/research.sqlite AGENDA_ID
python3 -m dd_research_runtime.agenda_cli export /path/research.sqlite AGENDA_ID /path/new-agenda.md
python3 -m dd_research_runtime.agenda_cli export /path/research.sqlite AGENDA_ID /path/new-agenda.json --format json
```

These commands read one verified SQLite snapshot without creating/migrating a missing
database or overwriting an existing destination/symlink. Research-controlled text is
escaped in Markdown. Planning does not mutate evidence, claims, workflow visits,
reports, receipts or gates, and does not make its own basis report stale.

Agenda freshness binds the research/workflow context, excluding gate bookkeeping and
other output/planning records. A separate gate review does not invalidate the research
plan or make its items executable. basis_report_current separately shows whether the
basis report's exact research/gate snapshot is still current. Changed research, a new
frame or a reopened/revisited workflow marks the agenda stale; original records remain.
Stale export needs --allow-stale and is labelled stale. Inspecting a stale plan is
allowed as historical context, not proof its gaps are still current or resolved.

The ordinary journal, authorization, revision and retry boundary applies. Checkpoints
preserve agendas. Previous supported cases/report hashes remain replayable; a genuine
unmodified Cycle 133 checkpoint is included in regression tests. Older writers do not
understand new plan_research commands; use the current reader/writer for those cases.

Limits: methods, feasibility, sample quality, ethical/consent requirements and validity
need actual human research judgment. No study is conducted or independently validated
by storing a proposal. The user-facing interface and actual final host acceptance remain
unfinished. The source ZIP is separate from the user's data and verified checkpoints.
