# Cycle 141 — record and retain open research questions

Built from verified Cycle 140 archive and unchanged baseline: 988 passed in 101.10s.
Define already supported explicit uncertainty selection, but a browser user could not
record those questions. The Interpretations section now saves an open question on its own
or atomically links it to selected existing interpretations. A new interpretation can
explicitly select existing uncertainties. Nothing is selected or resolved automatically.

Questions and saved statuses are visible alongside linked interpretations. An uncertainty
is a research record, not source evidence, a confirmed conclusion or an authorization.
New questions always start open. This interface cannot overwrite an existing uncertainty,
mark it resolved/closed or change claim dispositions. Source snapshots, source/synthetic
labels, existing phase findings, gate history and source-ledger revisions are preserved.

The adapter uses existing typed analysis transactions and revision checks. A question and
up to 99 interpretation updates share one commit, with no orphan question or partial links
on failure. Existing claim links are appended to, not replaced. Added analysis can make
reports or phase bases stale; original visit context remains available. No silent reframe,
phase progression, human approval or external execution is introduced.

See UNCERTAINTY_INTERFACE_GUIDE.md and TEST_RESULTS.md. Broader uncertainty lifecycle and
analysis editing remain library/host operations. Actual research and MVP-08 acceptance
remain pending at the user's request; engineering examples remain invented fixtures.
