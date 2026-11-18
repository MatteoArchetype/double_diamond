# Cycle 145 — revise advisory interpretations without rewriting history

Built from verified Cycle 144 archive and unchanged baseline: 1091 passed in 100.96s.
Interpretations could be created but not revised through the browser. Eligible advisory
draft/unresolved/unknown/hypothesis records now expose an explicit unsaved revision form.
The server derives eligibility from existing analysis status and conservative status/
disposition allowlists. Retained, qualified, narrowed, withdrawn, retracted, human-promoted
or unsupported records remain in their host workflow. Client display alone cannot authorize.

The form changes only wording, explicit evidence links and explicit uncertainty links, with
a fresh reason. Claim type, confidence, status, disposition, source records, workflow and
human gates cannot be patched. Existing typed update_claim transactions retain the complete
previous claim version and reason. The browser displays prior wording, earlier evidence
links and uncertainty counts without substituting current question text for earlier context.

Drafts are isolated from other forms. Navigation preserves the one unsaved revision; closing
it makes no write. Starting a revision replaces any other unsaved revision draft. A stale
case version is refused; unsaved wording remains visible for reference, not automatically
reapplied. An uncertain response requires inspecting saved research before retrying.

Changed claim context stales applicable assessments, phase findings and reports without
rewriting their original context. Revision does not approve a changed Define frame or
progress/reopen research; existing exact gates still apply. Checkpoints retain history.
See ADVISORY_REVISION_GUIDE.md and TEST_RESULTS.md. No core analysis, ledger, source, schema,
workflow or gate semantics change. Actual research and MVP-08 acceptance remain pending.
