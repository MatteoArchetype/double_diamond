# Cycle 151 — case discovery cannot initialize incomplete research

Built from verified Cycle 150 archive/source. Its prior full source run of 1185 tests
in 156.52s is reused as baseline, not claimed as a new run. A disposable reproduction
showed listing an empty database grew it from 0 to 57344 bytes via store initialization,
then raised RuntimeError and blocked the case list.

Discovery now uses the existing constructor-free read-only verifier. It validates case
metadata, isolates unavailable cases and preserves their files. Healthy cases remain
usable. Private staging/empty reservations are ignored, and case-file symlinks are refused.
An authenticated catalog endpoint provides healthy and unavailable summaries; the old list
endpoint retains its shape. The browser names unavailable cases and offers conservative
preservation/checkpoint guidance, without raw error details or automatic repair.

Sixteen new tests cover invalid/empty databases, malformed metadata, constructor refusal,
missing components, file symlinks, unsupported earlier workflow, authenticated routing,
healthy-list compatibility and concurrent case publication. No core source, gate, ledger,
workflow or schema semantics change. See TEST_RESULTS.md for final runs and browser QA.

Limits: generic diagnostics are not a corruption diagnosis; temporary locks may also
make a case unavailable. Case discovery is not a single global workspace snapshot.
Explicit library adoption/write paths are outside this read-only discovery fix. No
independent source/identity provider, hardware-power-loss or cross-platform validation.
Actual research and final MVP-08 human acceptance remain deferred.
