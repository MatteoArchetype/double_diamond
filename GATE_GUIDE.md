# Durable human gates — Cycle 129

Use PersistentEvidenceStore.apply_gate(command, operation_id=..., actor=...,
rationale=..., expected_state_revision=..., authorize=host_authorize).
The callback must return exactly True for gate_propose, gate_decide or gate_execute,
according to command type. The host authenticates actor IDs and controls permissions.
Fixture callbacks simulate identity; local hashes cannot establish a person's identity.

1. Propose: {type: propose, gate_id: ID, action: ACTION}.
2. Read the committed proposal and obtain explicit human review.
3. Decide: {type: decide, gate_id: ID, decision: approve|reject,
   proposal_digest: binding(ACTION)}. binding is imported from gate_transactions.
4. Apply the approved disposition through apply_analysis with gate_id added to the
   exact ACTION. analysis_write permission is still required. Consumption and the
   claim/disposition update commit together, or both roll back.

ACTION may be a supported set_disposition command (without gate_id). The proposal
is validated on an isolated state. Claim version and all command fields are bound.
Withdraw, promote_to_hypothesis and review_required/foundational/consequential
bounded dispositions require approval. Split is rejected until actual child-claim
semantics exist. Do not weaken review flags to avoid the human gate.

Alternatively ACTION is {type: gated_action, action: TYPE, payload: OBJECT}, where
TYPE is publication, primary_research, sensitive_access, consequential_action,
scope_change, material_reframing or phase_transition. Execute locally with
{type: execute, gate_id: ID, action: ACTION}, requiring gate_execute permission.
This records one authorization consumption; it does not publish, access a service,
change workflow records or perform external work. The host must include the exact
report/content/operation digest and scope in payload and enforce those bindings when
performing external work. No exactly-once external side effect is promised.

Pending/rejected/executed gates cannot authorize new actions. Changed action content,
type or relevant claim version fails. A stale claim needs a new proposal ID and a
fresh decision. All writes compare expected current state revision. Identical retries
with the original operation ID return the committed result after reauthorization;
changed requests conflict. Rejected gates are terminal; use a new proposal for revision.
The same authorized actor may propose and decide; separation of duties is host policy.

load_gate_operation(ID) returns the verified request, result, timestamp and journal
hash. mutation_coverage includes gate_mutations when gate entries exist; operations
in verify_integrity still counts evidence ingestions only. Gate events do not create
evidence review receipts. Ordinary detached/legacy approve_gate calls are insufficient
for durable action consumption: replay requires prior durable proposal/approve entries.

Use one current-cycle writer per database deployment. Cycle 128 readers cannot replay
new gate kinds. Existing validated journals and checkpoints remain readable by this
cycle. Back up research with the checkpoint API/CLI; the source ZIP has no user database.
Journal hashes detect local inconsistencies but are not an externally signed audit.
