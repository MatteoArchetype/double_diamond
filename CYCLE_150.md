# Cycle 150 — publish complete synthetic learning examples

Built from the verified Cycle 149 archive and unchanged source; its prior 1171-test
source suite in 133.99s is reused as the verified baseline, not claimed as newly run.
The browser learning-example creator still wrote directly into its final case folder,
although empty-case creation was already staged. Example creation now builds privately,
checks the completed fixture result and database, writes private synthetic metadata,
and uses the same exclusive reservation/publication helper as empty-case creation.

A partial builder failure or interruption before publication cannot expose an incomplete
case. A lost response after publication retains a complete, explicitly synthetic example.
Existing case identifiers never get overwritten. The fixture must report no live sources,
no MVP acceptance, passing checks, criterion-linked workflow and only synthetic evidence.
This does not turn fixture callbacks into real approval or independent source validation.

Fourteen new example tests plus thirteen existing empty-case tests cover builder failures,
three pre-publication boundaries, uncertain response, concurrent examples, collisions,
refusal of inappropriate fixture summaries, three abrupt subprocess exits and visibility/
private metadata. Shared publication retains the existing empty-case fault boundaries.
No browser UI, core ledger/source/gate/workflow rules or schemas change.

Limits: hard crashes may leave private staging or empty reservations; no automatic
adoption/deletion. Repeated deliberate requests can create separate examples; no exactly-
once cross-request semantics. Process exits do not establish hardware power-loss durability
or cross-platform filesystem behavior. Real research and MVP-08 acceptance remain deferred.
See TEST_RESULTS.md and RELEASE_STATUS.json for final engineering checks.
