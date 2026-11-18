Cycle 133: new version 3 cases link success criteria to Deliver evaluations and next research. See CRITERIA_GUIDE.md. The version 2 workflow below remains supported unchanged.

# Double Diamond research workflow — Cycle 132

This tool helps research move from broad exploration to a clear problem, competing
explanations or options, and an evidence-backed research decision. New learning can
send the work back to an earlier phase. Earlier findings stay visible.

Discover and Develop encourage exploration; Define and Deliver support convergence.
For this research tool, Deliver records the evaluation of a selected alternative and
a research recommendation, revision request or unresolved outcome. A report alone is
not a test result. Actual user research and experiments require real evidence; source
text, interpretations and synthetic examples remain distinct. No product launch or
external research action is implied by a saved decision.

Reference: https://www.designcouncil.org.uk/resources/framework-for-innovation/

## Run the learning-loop example

```sh
python3 -m dd_research_runtime.dd_demo --keep /path/to/new-example-directory
```

The example is explicitly synthetic, with simulated reviewers. It progresses through
all four phases, records an inconclusive comparison, escalates, reopens Define,
obtains a separate framing approval, revisits Develop and Deliver, then stops with
uncertainty. Seven immutable visits are retained. It writes research.sqlite, an
iteration-aware draft, demo-report.json, a verified checkpoint and restored database.
Existing destinations are refused. Default execution uses temporary files.

## New cases and compatibility

Use PersistentEvidenceStore.apply_workflow with the existing actor/rationale,
operation_id, expected_state_revision and host authorization callback. Exactly True
is required for workflow_write. Every new write compares the expected current
revision; identical retries return the earlier result after current authorization.
New cases start with type start_double_diamond, workflow_id, brief, scope, questions,
max_alternatives (2–20) and max_visits (4–20). Questions are 1–20 distinct nonblank
strings. Brief/scope/questions must be empty before initialization. The initial phase
is Discover; brief is setup, not a fifth research phase.

Existing version 1 cases keep their old commands, replay and report hashes. There is
no silent conversion or execution of earlier pending approvals. Version 2 is opt-in
and identifies methodology=double_diamond. Use this cycle's writer/reader for its
journal entries; older code does not understand the new commands.

## Phase records

Submit {type: record, phase: PHASE, record: RECORD}. A visit is recorded once. These
are advisory research records, not independently validated conclusions.

- discover: evidence_ids (nonempty), notes, perspectives (2–20 distinct descriptions)
  and limitations. Missing perspectives can be named as gaps; naming them does not
  claim interviews or independent corroboration occurred.
- define: problem, claim_ids (nonempty), uncertainty_ids and success_criteria
  (1–20 distinct descriptions).
- develop: alternatives (2 to max_alternatives), each with alternative_id, hypothesis,
  test, claim_ids (nonempty), evidence_ids and limitations. This phase preserves
  competing options and proposed tests rather than silently treating one answer as final.
- deliver: selected_alternative_id, evaluations, decision, summary, claim_ids and
  limitations. Each evaluation has evaluation_id, alternative_id, method, evidence_ids,
  outcome (supported / unsupported / inconclusive), and limitations. All alternatives
  must refer to the current Develop visit. The selected option must be evaluated.
  Supported/unsupported outcomes require evidence. recommend additionally requires a
  supported selected-option evaluation; revise requires iteration or escalation;
  stop_unresolved preserves an honest inconclusive outcome. Evaluations are host-
  recorded assertions; this library does not run or independently validate experiments.

Evidence origin is retained and shown in reports. A supported synthetic comparison
is still synthetic and cannot satisfy real-source host acceptance.

## Human-gated progression and iteration

Use transition_action(state, to_phase, reason) from double_diamond.py, then propose
and decide that exact action through the gate API. Supply the approved gate_id with
{type: advance|revisit|reopen, to_phase: ..., reason: ..., gate_id: ...}.
The reason and current research content are part of the approval binding.

advance moves one phase forward and needs a current recorded phase. revisit returns
to the current or any earlier phase while active. reopen does the same after a stop
or escalation. Every visit consumes the budget, including repeated visits. After the
budget is exhausted, stop if the research is complete or escalate; no automatic scope
expansion or unbounded retry occurs. Phase/reframing approvals require real host
identity and gate permissions; the example callbacks are simulation only.

A revisit supersedes the active records for its target and later phases. Original
visit records, reasons, versions, actions and approvals stay in the saved history.
They are not overwritten. Returning to Define therefore makes old Develop/Deliver
records historical; it cannot silently reuse their conclusions as the new result.

If a new Define visit changes the problem, selected claims/uncertainties or success
criteria, use
reframing_action(state, proposed_record) and obtain a separate material_reframing
approval. The record command includes that gate_id. A changed record, stale approval,
wrong gate type or reused decision fails. Merely returning to Define does not approve
a materially different problem frame.

Findings bind to referenced claims, evidence, sources and uncertainties. A new unrelated
claim does not invalidate every phase; changing a referenced claim or material
uncertainty does. Stale work needs a new visit. Transitions still bind the complete
research/workflow state, so a newly changed case needs a fresh transition approval.

## Finish, inspect and accept

Finish with {type: finish, outcome: stopped|escalated, reason: ...}. A completed stop
requires current records for all four phases and a Deliver decision other than revise.
Escalation can explicitly stop incomplete or budget-limited work. Create a new saved
report using the ordinary report command after stopping or escalation.

Reports show the latest findings, selected-option evaluations, synthetic origins,
iteration reasons and original/superseded phase visits. Old reports become stale after
reopening, while retaining their original contents. Export and checkpoint rules remain
unchanged. Host acceptance supports version 2 and checks real-source snapshots for
current and archived evidence references. It never accepts synthetic-only fixtures.

Limits: this is a bounded research workflow, not proof of methodology quality or an
autonomous experiment executor. Perspectives, criteria, tests and interpretations need
thoughtful human research. No graphical interface, user-study validation, external
publication or product delivery has been added. See PRODUCT_DIRECTION.md.
