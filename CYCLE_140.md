# Cycle 140 — separate Deliver evaluations

Built from verified Cycle 139 archive and unchanged baseline: 971 passed in 101.71s.
The browser previously accepted one evaluation per Deliver visit while the existing
research engine supported 1–20. That prevented users recording distinct supporting and
contrary evidence against different Define criteria in one research pass.

Deliver now records up to 20 separate evaluations, each with its own developed alternative,
method actually carried out, explicit evidence selection, outcome and limits. Criteria link
to one or more evaluations of the selected alternative. Links are never auto-selected;
changing alternatives or removing the last evaluation clears links that no longer apply.
Adding a row does not execute a test, retrieve evidence or approve research. Proposed tests
remain separate from completed evaluations. Failed/unknown criteria still require next
research, and a recommendation still requires all criteria met through the existing engine.

Draft row contents and links survive navigation within the current page. They remain
unsaved until explicit record submission, and do not survive browser reload. Retained
findings, original source context and draft reports use existing journal-backed inspection
and trace mechanisms. No schema, approval, identity, analysis or publication boundary changes.
Actual research remains untouched. See DELIVER_EVALUATIONS_GUIDE.md and TEST_RESULTS.md.
