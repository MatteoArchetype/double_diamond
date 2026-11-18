# Cycle 132 — research iteration grounded in Double Diamond

Built from unchanged Cycle 131 (709 passing baseline tests). At the user's direction,
the next work focuses on the research process: explicit Discover, Define, Develop and
Deliver phases, immutable phase visits and bounded human-gated revisits/reopening.
Material changes to the problem frame need a separate exact-content approval.

Discover records perspectives and gaps; Define adds success criteria; Develop retains
competing alternatives and proposed tests. Deliver now records the selected alternative,
evaluations and a recommend/revise/stop-unresolved decision. It is not just a report
label. The tool does not independently execute experiments or validate their truth.
Source fidelity, synthetic distinction, human gates, revision checks, idempotency,
SQLite recovery and checkpoint/journal validation remain intact.

The new seven-visit synthetic example learns from an inconclusive comparison, returns
to framing, preserves its first findings, and stops with explicit uncertainty after
refinement. Existing version 1 cases and historical report hashes are preserved.
The actual public-source case from Cycle 131 was not migrated or progressed, and no
pending human approvals or final acceptance were inferred from 'continue building'.

See DOUBLE_DIAMOND_GUIDE.md, PRODUCT_DIRECTION.md and TEST_RESULTS.md. Remaining work
includes making the research experience usable, gathering real empirical inputs and
actual host acceptance. No new cycle-count guarantee or full-methodology certification
is claimed. This code package is separate from the user's research databases.
