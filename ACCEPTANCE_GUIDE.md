# Host-checked acceptance guide

This guide describes the manual acceptance path for MVP-08 in
[`MVP_ACCEPTANCE.json`](MVP_ACCEPTANCE.json). It is a procedure, not an
acceptance result. The public-source packet in
[`PUBLIC_SOURCE_CASE.json`](PUBLIC_SOURCE_CASE.json) is still an unapproved
candidate; completing these steps requires an actual human reviewer and
independent source acquisition.

## Important boundary

The application is a local, single-operator tool. This repository does not
provide an independent identity provider or a production host that authenticates
reviewers. The browser app does not expose a host-acceptance screen or route.
`dd_research_runtime.acceptance_cli` can prepare an unapproved candidate and
inspect a saved report; it cannot approve it.

The Python authorization callbacks used by tests are simulations. Do not use a
test callback, a locally invented actor identity, or a fixture to claim
authenticated human acceptance. A trusted host or operator must authenticate
the reviewer and enforce the two permissions described below before recording
an acceptance. Until that is available, MVP-08 remains pending.

## 1. Prepare an independently reviewed source set

1. Agree on a bounded research question and scope. State what the case will not
   establish, such as a claim about a specific machine, deployment, or user
   population that is not actually tested.
2. The human reviewer independently opens the full original sources, rather
   than relying on the excerpts or summaries in the candidate packet. Record
   the access time with timezone, acquisition method, source URL, title,
   publisher, relevant section/page, and enough surrounding context to assess
   the passage.
3. Check that each passage supports the interpretation attributed to it.
   Record uncertainty and counterevidence. Identify shared publishers or other
   dependencies; multiple pages from one publisher are not independent
   confirmations.
4. Preserve source snapshots through the normal reviewed-ingestion path.
   Source approval is a human decision. Keep synthetic material labeled and
   separate from real evidence.

For the current SQLite packet, independently re-open both linked pages and
check their current full context. They are both from the SQLite project, their
captured excerpts are short, and the packet's acquisition date is
2026-10-22. Treat them as one publisher cluster and reacquire/record current
context; the packet itself does not establish independent acquisition.

## 2. Run and review one bounded case

1. Create a research case for the agreed question and add only the sources
   actually reviewed. Retain exact passages and locations; do not promote
   source leads directly to evidence.
2. Work through Discover, Define, Develop, and Deliver. Save each stage's
   evidence, interpretations, criteria, alternatives, evaluation, limitations,
   and next research as applicable.
3. Make phase-transition and reframing decisions through the normal human
   review gates. A gate approval authorizes only its specific transition; it
   is not final case acceptance or publication approval.
4. Stop the bounded workflow and save a current **draft** report. Do not
   publish it as an approved research result.
5. Have the authenticated reviewer check the report against the retained source
   passages, interpretations, uncertainties, and limitations. Correct the
   case and regenerate the report if anything changes.

## 3. Check structural readiness

Run the read-only inspector against the case database and saved report ID:

```sh
python -m dd_research_runtime.acceptance_cli inspect \
  "<workspace>/<case-id>/research.sqlite" "<report-id>"
```

Use the workspace's Python environment if one is active (for example,
`.venv/bin/python` on macOS/Linux or `.venv\Scripts\python.exe` on Windows).

Review the output, including `structurally_ready`, `blockers`,
`source_bindings`, `report_digest`, and `state_revision`. Structural readiness
only confirms that the saved report and evidence meet software checks. It does
not verify source truth, reviewer identity, acquisition independence, research
quality, release readiness, or publication authorization. If blockers remain,
resolve them and inspect the new current report; never bypass them.

## 4. Record the authenticated host decision

Only the trusted host integration may submit a host decision. Before it calls
`PersistentEvidenceStore.apply_acceptance`, it must:

- Authenticate the human reviewer and pass the authenticated actor and rationale.
- Authorize `acceptance_record` for the decision.
- For an acceptance (`decision: "accept"`, `review_mode: "host"`), separately
  authorize `acceptance_confirm_real_sources`.
- Obtain an explicit human decision after review; never infer acceptance from
  a successful workflow, report, or readiness check.
- Bind the command to the exact current `report_id`, `report_digest`, and
  inspected source bindings. Include one source attestation for every retained
  real-source binding, with its matching evidence ID, ingestion operation ID,
  snapshot digest, and source URL, plus acquisition time, acquisition method,
  and the basis for the independence assessment.
- Record explicit limitations and a unique operation ID. Preserve the
  resulting append-only audit record.

An accepted decision is scoped to the bounded case. It does not certify the
software release or authorize publication. A later research change can make
the report and its acceptance stale; re-inspect and obtain a new review rather
than reusing the old decision. A rejection is also a valid human outcome and
must leave MVP-08 pending.

Do not invoke the host mode through a locally supplied permissive callback.
Without a trusted host integration that performs the authentication and
authorization above, stop here and record the integration gap; do not mark the
case host-accepted.

## 5. Preserve the outcome and update acceptance status

Keep the reviewed source material, saved report, phase decisions, limitations,
review rationale, host-authenticated acceptance operation, and final inspector
output together as the acceptance record. Protect the workspace and exported
research data as sensitive local files.

Update `MVP_ACCEPTANCE.json` only after a real host-authenticated acceptance,
the required full regression suite, and packaged-source verification have all
passed. Record the actual result and limitations; do not substitute fixture
checks or this guide for the host-checked case. If the case is rejected or the
host integration is unavailable, leave MVP-08 as `manual_acceptance_pending`
and document the blocker.
