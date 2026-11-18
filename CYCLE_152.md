# Cycle 152 — opening research is an inspection, not initialization

Built from verified Cycle 151 archive/source. Its prior full source run of 1201 tests
in 164.96s is reused as baseline, not claimed as a new run. Disposable reproduction
confirmed case opening still grew an empty database to 57344 bytes before failing,
even though discovery was fixed. The report download route used the same constructor.

Case opening now validates metadata without following metadata symlinks, then uses the
existing constructor-free read-only database verifier. Saved-report download reads the
verified retained output through the same read-only helper and preserves existing Markdown
rendering. Direct links to incomplete files cannot initialize tables or adopt history.
Write operations remain explicit through their existing capability/revision boundaries.

Sixteen new tests cover incomplete state/report files, constructor refusal, malformed
metadata before database access, metadata symlink refusal, authenticated HTTP state/report
access, saved Markdown equality, checkpoint recovery, concurrent consistent snapshots,
detached returned state and supported pre-journal inspection with no schema adoption.
No browser UI, core source, ledger, gate, workflow or schema rules change.

Limits: generic read failures do not diagnose corruption; access/locking/unsupported
formats can also prevent opening. No global workspace snapshot, automatic repair,
hardware-power-loss or cross-platform validation. Explicit library adoption/write APIs
are outside this read-only change. Actual research and final MVP-08 human acceptance
remain deferred. See TEST_RESULTS.md and RELEASE_STATUS.json for final engineering runs.
