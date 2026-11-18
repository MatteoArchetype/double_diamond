Cycle 133 adds criterion-linked research decisions to the bounded Double Diamond workflow. See CRITERIA_GUIDE.md. Evidence quality, research design and actual validation remain human responsibilities.

# Current scope update — Cycle 132

New version 2 cases now support explicit Discover/Define/Develop/Deliver, bounded iteration and reopening, framing approvals and selected-option evaluations. This is a research tool; actual evidence, research quality and experimental validity remain human responsibilities. See DOUBLE_DIAMOND_GUIDE.md.

The earlier scope statement below describes version 1, which existing cases keep unchanged.

# Relationship to the Double Diamond

The current release implements a bounded research workflow inspired by the Double
Diamond. It is not a complete implementation of the Design Council methodology.

The Design Council describes Discover, Define, Develop and Deliver, with exploration
and convergence, people-centred work, testing/refinement and iteration. Reference:
https://www.designcouncil.org.uk/resources/framework-for-innovation/

The current runtime's scope is narrower:

- Brief is setup rather than a fifth Double Diamond phase.
- Discovery supports reviewed evidence intake; it does not require or conduct the
  breadth of user engagement associated with a full Discover phase.
- Definition records a bounded problem frame, claims and uncertainty.
- Alternatives records multiple interpretations/test outcomes. This supports part of
  Develop; the runtime does not automatically prototype or co-design solutions.
- Synthesis creates a bounded conclusion and report. It is not a substitute for the
  preferred-solution testing, refinement and implementation involved in Deliver.

The current saved workflow is deliberately one pass, with one record per phase;
corrections needing repeated phases use a new bounded case. It does not implement
Double Diamond's full iterative movement between phases. Human gates control the
runtime's transitions; approval does not make the workflow methodologically complete.

The public SQLite example is a documentation-reading acceptance case for the bounded
runtime, not a completed Double Diamond design project. Its comparison of two
interpretations is not a prototype or empirical test. Accepting that case would
validate the stated research-runtime scope only. It would not establish delivery of
a design solution or full methodological coverage.

No new implementation phase or broader methodological scope has been silently added
to the fixed MVP contract. These limitations need to stay visible when deciding whether
the bounded MVP meets the intended product goal. The human question about methodology
is not approval of the proposed research transitions or final acceptance.
