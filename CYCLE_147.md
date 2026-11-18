# Cycle 147 — outdated reviews no longer block useful navigation

Built from verified Cycle 146 archive. The engine correctly refused old approvals after
research changed, but browser guidance still sent users to apply them. A read-only
context match now distinguishes current proposals from outdated pending/approved history.
Guidance counts only matching proposals as next work, and reports old reviews separately.
The Approvals section retains history but removes outdated approve/apply controls. Pending
outdated proposals can be explicitly rejected. Matching proposals use existing separate
proposal/decision/application transactions and all core validation.

Old material-framing reviews display original reference IDs rather than substituting
current interpretation/uncertainty text or a possibly different preceding-frame comparison.
No source, claim, workflow, gate, schema or journal semantics changed; content matching is
advisory display logic, not permission or a prediction that application will succeed.

Eleven new integration tests cover both gate types, pending/approved states, restart and
checkpoint recovery, historical record preservation, fresh proposals alongside old gates,
explicit rejection, no-write inspection, missing bindings and unrelated gate types.
Initial test development assumed an unsaved reframing visit was a stale saved finding;
four assertions were corrected to expect the proper open Define work. No failed case was
removed. See TEST_RESULTS.md and RELEASE_STATUS.json for final results and browser QA.

Limitations: single local operator, synthetic verification only, no independent source or
identity authentication, hardware power-loss test, cross-platform/browser matrix or final
MVP-08 acceptance. Historical approval status is retained even when its context is outdated.
Matching context does not bypass budget, phase or saved-finding checks. Actual research
remains deferred at the user's request.
