# Inspect the research before deciding

Cycle 136 makes saved Double Diamond work inspectable in the browser. Clicking a phase
opens its latest visit; expanding Research history lets you inspect any earlier visit.
Inspection does not move the research, create a proposal or approve a change. Return to
current research to continue work. The decision controls always name the actual phase.

## What you can inspect

- Discover: observations, perspectives and missing voices, limitations and linked passages.
- Define: the problem, success criteria, advisory interpretations and linked uncertainties.
- Develop: every competing alternative, proposed test, assumptions, interpretations and evidence.
- Deliver: the selected alternative, recorded evaluation methods/outcomes/limits, each
  criterion's assessment and evaluation links, next research and included interpretations.
- Expand a retained source to see its exact passage, locator, title, author/publisher,
  URL, retrieval time, shared origin group and explicit synthetic label.
- Inspect an interpretation to see the evidence it linked at the time. The main
  Interpretations section separately displays links in the current research.
- Compare a repeat visit with the prior visit's immutable record. Changed sections are
  named; Define displays the earlier problem and success criteria. Inspect the earlier
  visit itself for its original source/interpretation context. This is not a full line diff.
- Expand the original question and boundaries to see the scope that applied when the
  finding was saved. The case header describes the currently loaded research.

## Original context, not a reconstruction from current claims

The inspection API reads one pinned, read-only SQLite snapshot, verifies the complete
existing audit history, locates the visit's recorded operation and checks its exact
record and context binding. Referenced interpretations, uncertainties, evidence and
source metadata come from that committed snapshot. Later claim edits cannot silently
replace them. Findings remain advisory; local integrity is not independent identity or
source verification and does not establish that an explanation is true.

A visit may still be part of the current research while its referenced interpretation
has changed. The interface marks that finding for review. An earlier visit is labelled
historical even if a later visit saved identical text. Open visits do not invent findings.
Pre-journal/bootstrap records can show their saved content but explicitly report that
the original context is unavailable; current references are never substituted.

A changed browser revision is refused. Refresh the case and review it again. Reading
never repairs, migrates, accepts or writes research. No independent source acquisition,
source snapshot viewer, final acceptance or publication action is introduced.

## Library and offline demonstration

```
from dd_research_runtime.visit_review import read_visit
review = read_visit('/absolute/path/research.sqlite', 'V2', expected_revision=17)
```

Omit expected_revision for an independently pinned read, rather than a browser-aligned
inspection. Results are detached data; changing them does not edit the database.
`context_status` is `verified_original`, `not_recorded` or `unavailable`.

Run the clearly synthetic demonstration:

```
python3 -m dd_research_runtime.visit_review_demo
```

The demo checks original and revised frames, exact comparison, current/historical labels,
synthetic passages, criterion/evaluation context and unchanged database bytes. It does
not satisfy real-source or human acceptance requirements.
