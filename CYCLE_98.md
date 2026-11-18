
# Cycle 98 — Stopping and Escalation

The agent does not stop because it has reached a source count. It stops
when remaining uncertainty is unlikely to change a decision or conclusion.

The stopping assessment considers:
- decision relevance;
- unresolved uncertainty;
- expected information gain;
- potential to change the conclusion;
- materiality of evidence gaps;
- pending human gates.

Material gaps that could change a conclusion trigger targeted research.
Pending human gates always stop autonomous execution.
Ambiguous high-consequence cases escalate for human judgement.

Every stopping decision requires a recorded rationale.
