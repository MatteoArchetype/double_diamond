# Cycle 149 — publish complete new research cases

Built from the verified original Cycle 148 archive and unchanged application source.
Its most recent full regression passed 1158 tests in 172.67s during the shortcut repair;
that baseline result is reused, not represented as a new baseline run.

Empty-case creation previously wrote directly into its visible identifier directory.
An interrupted attempt could leave a partial case hidden by the case-list error handling.
Creation now stages the initialized database, bounded Discover workflow and private case
metadata, verifies state/ledger revisions and workflow identifier, then publishes using
an exclusive empty reservation and same-filesystem directory replacement. Failures cannot
overwrite existing cases. A complete publication survives an uncertain response.

Thirteen new tests cover four exception boundaries, post-publication lost response,
concurrent creation of eight distinct cases, identifier collision, four abrupt process
exit boundaries, validation before staging and visibility/permissions around publication.
No UI, evidence-ingestion, audit-ledger, gate, workflow or schema rules changed. Source
integrity and synthetic distinction remain unchanged. Actual research is deferred.

Limits: private staging/empty reservations may remain after a hard crash; no automatic
cleanup/adoption. No exactly-once semantics across separate creation requests, hardware
power-loss proof or cross-platform validation. Synthetic-example creation is outside this
fix; checkpoint restore keeps its existing separate boundary. MVP-08 remains pending.
See TEST_RESULTS.md and RELEASE_STATUS.json for final source/extracted checks.
