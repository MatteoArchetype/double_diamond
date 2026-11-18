# Persist advisory analysis

Use Python 3.10+ and the current cycle source. Runtime operations use the standard
library. Host authorization is required; a real integration must supply its own
identity/access implementation, not copy a fixture allow-list as authentication.

```python
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore

store = PersistentEvidenceStore('/path/to/existing-research.sqlite')
state, revision = store.load()
result = store.apply_analysis(
    [{'type': 'add_claim', 'record': {
        'claim_id': 'claim-1',
        'claim': 'A bounded interpretation requiring further evidence.',
        'claim_type': 'descriptive',
        'disposition': 'unresolved',
        'status': 'unresolved',
        'evidence_ids': [],
    }}],
    operation_id='analysis-request-1',
    actor='authenticated-actor-id',
    rationale='Record an explicit unresolved interpretation.',
    expected_state_revision=revision,
    authorize=host_authorize,
)
```

host_authorize(actor, 'analysis_write') must return exactly True. Defining that callback
and obtaining an authenticated actor is the host's responsibility. No analysis method
approves a source, authorizes publication or persists a gate decision.

The operation ID, actor, rationale and commands form retry identity. Retrying the same
request with the same operation ID returns the original result, even after later writes;
current authorization is still required. A changed request conflicts. Revisions apply
to new operations, and no stale revision is silently refreshed. pending/ operation IDs
are reserved for reviewed queue ingestion. Operation IDs cannot cross analysis/ingestion.

## Supported commands

- add_claim: record with claim_id, claim and optional claim_type, evidence_ids,
  disposition, status, confidence and material_uncertainties. Initial state is advisory
  draft/unresolved/hypothesis; finalized/human-sensitive dispositions are not accepted.
- update_claim: claim_id and a bounded patch of claim, claim_type, evidence_ids,
  confidence or material_uncertainties. Identity, status, disposition and arbitrary
  state/gate/source fields cannot be patched. New belief history is recorded.
- assess_evidence: assessment_id, claim_id, evidence_id, all assessment.DIMENSIONS,
  limitations and rationale. Qualitative values are low/medium/high/unknown/not_applicable.
  The evidence must already be attached to that claim. Output is advisory, actor-labelled
  and bound to the exact claim/evidence digests. assessment_is_current(state, id) from
  analysis_transactions detects staleness after changes; it does not approve a claim.
- add_contradiction: record with contradiction_id, claim_a, claim_b and issue, with
  optional disposition/resolution_basis. Claims must exist and be distinct.
- update_contradiction: contradiction_id and patch of issue/disposition/resolution_basis.
  Resolved/narrowed/qualified/withdrawn records require a nonblank resolution basis.
- put_uncertainty: record with uncertainty_id, question, status and optional resolution_basis.
  Closed/resolved status requires a basis. Replacing a record is explicit and journalled.
- set_disposition: disposition_id, claim_id, disposition, rationale, evidence_ids,
  prior_status, new_status, material_uncertainties and decision_relevance; optional
  review_required/foundational/consequential flags. Non-gated outcomes are
  retain_bounded→retained, narrow→narrowed, qualify→qualified, unresolved→unresolved/unknown.
  Withdrawal, hypothesis promotion and flagged human-review cases require the exact
  approved durable gate_id. Split remains unsupported. Ingestion/analysis permission
  alone cannot authorize those changes.

Commands in one request execute sequentially on an isolated state; later commands may
reference earlier records. All commands commit together or none do. There must be 1–100
commands and the canonical request must not exceed 2 MiB. Referenced evidence, claims
and uncertainties must exist; causal/generalisation claims need evidence or an explicit
unresolved/hypothesis state. Origin labels and advisory status are derived, not supplied
by callers. Synthetic evidence remains synthetic; the API cannot edit evidence/sources.

## Inspect and recover

store.load() returns detached state. New assessments are in state.assessments and
advisory disposition records in state.claim_dispositions. Older states may not contain
these collections until used. Direct edits to a loaded object still do not persist.

store.load_analysis_operation(id) returns the recorded request/result, timestamp and
journal entry hash. store.mutation_coverage() reports adoption revision and counts of
new ingestion/analysis journal entries. Existing verify_integrity().operations and
checkpoint summary.operations continue to count ingestion operations; state revision
now advances for analysis too. New checkpoint summaries include state_mutations.

Existing databases are adopted at their current verified state into a local checkpoint.
Historical evidence operation IDs, result revisions, review coverage and retries remain
unchanged. New mutations are replayed from that adoption checkpoint on integrity reads.
No historical reviewer identity or missing review body is invented. Use this cycle
or newer for writes after adoption; older ingestion writers do not journal their
changes and must not be mixed with the new store. New checkpoints
require this cycle or newer for the added journal schema; older checkpoint formats are
still readable and can be explicitly adopted after restoration.

Current data and full journal snapshots are plaintext. Hash chains are not signatures
or external anchors. Full-state history/replay has growing storage and verification
cost. See CYCLE_129.md for the exact scope and remaining limitations.

Cycle 129: sensitive withdraw/promote and flagged bounded dispositions accept gate_id only after exact durable approval. See GATE_GUIDE.md. Split remains unsupported: recording a split without child claims would misrepresent the operation.
