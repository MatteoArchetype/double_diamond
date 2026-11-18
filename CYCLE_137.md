# Cycle 137 — revise the problem frame without losing review boundaries

Built from unchanged Cycle 136, with 883 passing baseline tests. Verification focuses
on the tool, using synthetic cases; the user's healthcare question remains untouched.

The interface can now explicitly copy an earlier, inspected Define frame into an unsaved
form after a reviewed return to Define. Problem, criteria, interpretation links and
uncertainty selection are preserved exactly. Linked uncertainties are explicitly selected
rather than automatically including every uncertainty in the case. A fresh saving reason
is required. Copying creates no finding, receipt, gate, report or approval.

Changed frames still use the existing content-bound proposal/decision/application path.
The review shows previous and proposed problem/criteria and changed sections, with an
inspection link to the preceding original context. Restart preserves pending proposals
and decisions; checkpoint restore preserves that same boundary. A repeated research pass
must reassess Develop and Deliver before a new report can be current.

No schema or transaction changes are introduced. The read-only draft helper uses one
verified pinned visit snapshot and an expected case revision, refuses unavailable original
context and disallows copy outside an open Define visit. The original record stays immutable.
This is a concrete usability fix for Double Diamond iteration, not a new research method.

See FRAME_REVISION_GUIDE.md and TEST_RESULTS.md. Draft autosave, richer analysis editing,
multi-evaluation Deliver forms, external execution and independent identity verification
remain outside this cycle. Real-source/user acceptance is still pending; test counts are
software verification and do not establish real findings or final MVP acceptance.
