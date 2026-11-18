# Cycle 146 — verify revision, human decision and recovery boundaries

This is a verification release built from the verified Cycle 145 archive, not a new
research feature. Seven new integration tests exercise interpretation revisions across
Double Diamond phase review, material reframing, process restart and checkpoint recovery.
All evidence and human decisions in these tests are explicitly simulated.

An old approved transition cannot advance a changed interpretation, even after its frame
is reconsidered in a separately reviewed new visit. Existing saved visits cannot be
rewritten. A new transition proposal and separate decision/application are required.
An old material-reframing approval cannot apply against changed research; a replacement
proposal remains pending until its own explicit decision. Checkpoint recovery preserves
these boundaries and does not grant a new approval.

Repeated interpretation revisions preserve every prior wording and source link, original
visit contexts, stored reports, source snapshots and synthetic labels. Removing all
current support marks the interpretation unsupported rather than rewriting old findings.

No runtime, UI, workflow, gate, ledger or schema implementation changed. The tests exposed
no runtime defect. During test development an attempted in-place rewrite was correctly
refused; the scenario was corrected to use a separately reviewed revisit. See
TEST_RESULTS.md and RELEASE_STATUS.json for final verification results.

Limitations: synthetic engineering checks are not independent source authentication,
actual-user validation, hardware power-loss tests or final MVP-08 acceptance. Old gates
can retain an approved historical status while their application is refused against
changed research. Unsaved browser drafts still do not survive reload. Actual research
remains deferred; no real phase decision, final acceptance or publication is inferred.
