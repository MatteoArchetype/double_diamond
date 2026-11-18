# MVP completion contract and remaining backlog — Cycle 152

The target is a local Double Diamond research tool with a first single-operator
browser interface, Python library and documented commands. It is not a hosted service
or unattended agent with built-in independent identity/source providers. MVP_ACCEPTANCE.json is the machine-
readable contract. Optional scope is still deferred unless explicitly requested.

## Current required criteria

- MVP-01: Reviewed, traceable evidence intake — fixture verified.
- MVP-02: Durable advisory claims, assessments, contradictions, uncertainties and
  dispositions — fixture verified in Cycle 128. Human-sensitive disposition changes
  require exact durable gate approval; analysis permission alone cannot authorize them.
- MVP-03: Durable authenticated gate proposals and approve/reject decisions scoped
  to the intended action — fixture verified in Cycle 129.
- MVP-04: One bounded, persistent brief-to-synthesis research workflow — fixture verified in Cycle 130.
- MVP-05: Readable, source-traceable research report distinguishing evidence,
  interpretation, hypothesis, uncertainty and synthetic material — fixture verified in Cycle 130.
- MVP-06: Recovery, retry and checkpoint preservation — fixture verified.
- MVP-07: Runnable offline fixture and guide — fixture verified.
- MVP-08: Host-checked bounded real-source case after integration with authenticated
  review and explicit acceptance — manual acceptance pending.

Fixture verification is engineering evidence, not a real-source acceptance case or
authenticated human approval. The full MVP remains incomplete. Passing a larger test
suite alone is not the stopping condition.

## Completed foundation

Cycle 128 adds typed advisory analysis writes, an adopted-state checkpoint and replay
journal shared with new ingestion mutations. State revisions can advance independently
of evidence receipt counts, while legacy histories/retries are preserved. Checkpoints
include and validate the new journal. Assessments retain exact claim/evidence version
bindings; stale assessments are detectable rather than silently reused as current.
Direct edits to a loaded state remain detached, including gate approvals.

## Remaining human acceptance work

Cycle 131 implements the exact-report host acceptance boundary, retained-source
attestations, read-only inspection and an unapproved real public-source candidate.
The user selected the small public-source example for review. Its source review was explicitly approved in the desktop chat and the two-source
intake is committed; actual human workflow transition decisions and final acceptance
remain pending. Agent acquisition and simulated callbacks do not satisfy these human steps.

No additional implementation cycle is assumed. Finish the required case using the
current APIs and host integration; fix blocking defects if discovered. The remaining
work is measured by MVP-08, not by an invented cycle countdown. See ACCEPTANCE_GUIDE.md.

## Stopping rule and deferred work

Stop MVP development when all eight required criteria are satisfied, full regression
passes, the extracted package runs and host acceptance is recorded. New work must meet
a criterion, fix a blocking defect or follow an explicit user scope change. Defer broader GUI features,
service hosting, provider integrations, external exactly-once execution, scheduled/remote
backups, cryptographic anchoring and general scaling work. No behavioural economics
framework is assumed or invented.

Cycle 129 completes durable proposals, decisions and bounded local gate consumption. External execution remains a host responsibility.

Cycle 130 adds durable stage progression, content-bound human pauses, stop/escalate and traceable draft exports. MVP-08 remains required; fixture success cannot substitute for host acceptance.

Cycle 131 engineering is packaged separately from the pending actual-source review handoff. No fixture or public-source draft is silently promoted to human acceptance.

## User-directed research workflow work in Cycle 132

Version 2 adds four explicit Double Diamond research phases, bounded iteration,
immutable visit history and selected-alternative evaluations. This advances research
behavior rather than just storage infrastructure. Legacy cases and their pending
human decisions remain unchanged. The prior public-source case is still paused;
MVP-08 has not been completed or inferred from the new synthetic example.

Cycle 133 connects defined success criteria to selected-option evaluations and evidence; gaps now name next research. Earlier cases and pending human decisions are preserved. The unfinished interface, actual research inputs and host acceptance remain open.

Cycle 134 turns failed/unknown criteria into saved proposed research with evidence gaps, methods, priorities and dependencies. It does not authorize interviews/experiments, execute research, reframe cases or complete pending host acceptance.

Cycle 135 adds the user-directed first local interface. A real research case, actual user review, blocking usability fixes and explicit host acceptance remain the next completion work. The old public-source candidate remains paused; no pending decisions were inferred.

Cycle 136 closes the saved-finding inspection gap: complete phase records, original journal-bound source/interpretation context and repeated-frame comparisons. The healthcare/AI walkthrough is initialized as an empty Discover case; no research or human acceptance is claimed.

Cycle 137 improves the user-directed verification of the tool: explicit unsaved Define-frame copying, selected uncertainty links, visible before/after review and restart/checkpoint tests of pending revisions. The healthcare case remains untouched; real research is deferred until tool verification and user readiness.

Cycle 138 removes the terminal-only learning-example entry and adds advisory state-aware navigation. It supports verification with invented material; it does not satisfy real-source acceptance or perform actual research.

Cycle 139 adds browser checkpoint recovery. Cycle 140 closes the Deliver evaluation gap using existing research validation and human boundaries. Actual research and host acceptance remain deferred at the user’s request.

Cycle 141 closes the browser open-question entry gap. Questions and explicit interpretation links use atomic advisory transactions; Define selection, reframing review and final acceptance remain separate. See UNCERTAINTY_INTERFACE_GUIDE.md.

Cycle 142 closes the browser unresolved-disagreement entry and report-inspection gap. Distinct interpretations and source origins are preserved; resolution, research judgments and host acceptance are not inferred. See DISAGREEMENT_INTERFACE_GUIDE.md.

Cycle 143 closes the browser evidence-fit assessment gap. Ratings remain advisory, exact-version-bound and distinct from source intake, accepted claims, human gates and empirical validation. See EVIDENCE_FIT_INTERFACE_GUIDE.md.

Cycle 144 fixes shared Develop selections by giving each competing alternative explicit independent interpretation/passage links and structured drafts. Existing phase transactions and human gates are unchanged. See DEVELOP_ALTERNATIVES_GUIDE.md.

Cycle 145 closes advisory draft interpretation revision in the browser while retaining history and exact-context staleness. It does not expose claim decision changes or replace human phase/framing gates. See ADVISORY_REVISION_GUIDE.md.

Cycle 146 adds cross-feature regression coverage for stale transition/reframing approvals after advisory revisions, including checkpoint recovery and original-context preservation. No runtime or interface behavior changed; real research and human acceptance remain deferred.

Cycle 147 fixes outdated approval navigation: read-only content matching separates old review history from current research work. Original decisions persist and core gates remain authoritative. Actual research and final acceptance remain deferred.

Cycle 148 exposes read-only retained source text/review context in Sources. Missing historical records stay unavailable; no source authenticity, human acceptance or new approval is inferred. Actual research remains deferred.

Cycle 149 makes empty-case creation publish only after verified database and metadata staging. Interrupted cases are absent or complete; crash remnants are not adopted. Research behavior, human gates and final acceptance remain unchanged.

Cycle 150 extends staged publication to synthetic learning-example creation, reusing the verified reservation boundary for empty cases. Synthetic labels and simulated decisions remain separate from real acceptance; no actual research is performed.

Cycle 151 makes case discovery read-only and reports unavailable saved cases separately, preserving healthy-case access and original files. No migration/repair/approval is performed by listing. Actual research and final acceptance remain deferred.

Cycle 152 extends constructor-free read-only verification to case opening and saved-report download. Browser inspection no longer initializes/adopts/migrates these files. Write paths, methodology and human acceptance remain separate.
