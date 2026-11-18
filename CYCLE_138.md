# Cycle 138 — first-run learning and state-aware navigation

Built from unchanged Cycle 137 with 905 passing baseline tests. This cycle continues
verification of the tool itself; actual research questions remain untouched.

A fresh local workspace can now create a clearly labelled synthetic learning case from
the browser. The same option is available beside the new-case form for an existing
workspace. Creation uses the existing offline example, including explicit synthetic
labels and simulated historical approvals. It cannot seed a real case or infer actual
human acceptance. Existing research remains separate; repeated deliberate requests create
separate examples, with no automatic retry or request deduplication claimed.

A read-only Where you are panel derives its next navigation step from the verified saved
case: current phase, retained evidence, advisory interpretations, saved records, current
report status, research reviews and remaining visits. It highlights pending reviews,
approved-but-unapplied changes, stale findings and incomplete escalated work. It does not
make research judgments or grant permissions. Viewing the guidance causes no mutation.

The panel preserves the Double Diamond sequence and its bounded iteration. A saved stage
is labelled saved, not validated. A final open visit may still be recorded; an exhausted
budget is not silently expanded. Publication and external actions remain separate.

Browser verification also found older drafts preceding current results. Reports now
shows current drafts first, newest first, while preserving historical drafts and their
labels. Proposed follow-up research uses the newest current report by default. New-case
creation also retains its case link in the browser so reopening does not silently select
a different saved case.

No schema, research transaction, identity provider or external executor is added. The
synthetic-example endpoint uses existing private-session Host/Origin/token checks and
strict request fields. FIRST_RUN_GUIDE.md explains entry, synthetic limits and navigation.
See TEST_RESULTS.md for exact checks. Unsaved-draft persistence, broader analysis editing,
multi-evaluation Deliver forms and actual user acceptance remain open.
