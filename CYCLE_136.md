# Cycle 136 — inspect the research and its original context

Built from unchanged Cycle 135 with 851 passing baseline tests. The phase buttons now
open read-only saved visits rather than returning indistinguishable summaries. Earlier
visits expose complete phase findings, linked advisory interpretations, exact passages,
source metadata, assumptions, evaluations and criterion-linked decisions. Repeat visits
show which record sections changed; historical Define frames show the prior question
framing and criteria. The original question and scope remain inspectable.

A read-only API retrieves the recording operation from the verified persistent journal,
binds it to the immutable visit, and resolves references from that original committed
snapshot. It never borrows current claims to fill historical gaps. Bootstrap/pre-journal
records explicitly report unavailable original context. Browser revisions are checked;
concurrent writes do not produce mixed snapshots. No schema or research-write protocol
changes, migration, approval inference or changes to an existing case are required.

The user selected “How might healthcare change as a result of AI?” for the real walkthrough.
A separate local workspace now contains that question as an empty, provisional Discover
case. No source intake, finding, transition approval, acceptance or publication is inferred.
Its private research data are excluded from this release. The old acceptance candidate
and existing examples remain unmodified. The release includes only synthetic fixtures.

This cycle closes a concrete review gap in the first interface; it does not add a new
methodology or replace real research with engineering checks. UI limitations from Cycle
135 remain: one evaluation per Deliver visit, limited analysis editing, single operator,
no independent identity provider or external execution. Actual real-source/user acceptance
and empirical validity remain open. See VISIT_REVIEW_GUIDE.md and TEST_RESULTS.md.
