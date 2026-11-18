# Cycle 129 — durable human gate decisions

Built from verified Cycle 128 (584 tests). Gate proposal, approve/reject and local
consumption transactions share the revision-checked SQLite mutation journal with
analysis and evidence intake. Authorization is checked for each call and retry.
Proposals bind exact action content; claim dispositions additionally bind the target
claim version. Sensitive disposition changes consume approval atomically with the
claim update. Replay requires durable proposal/decision lineage and verifies every
result and state snapshot. Recovery supports failed writes and lost commit responses.
Source passages, synthetic flags and evidence receipts are unchanged by gate writes.

MVP-03 is fixture verified. The full workflow/report and host-checked real-source
acceptance remain open; MVP readiness remains false. Two targeted cycles remain,
conditional on the fixed acceptance contract. See GATE_GUIDE.md and TEST_RESULTS.md.

Limitations: host callbacks supply real authentication and access policy; all demos
simulate identity. No external action executor, live-source acceptance, publication,
research-result validation, signed audit, hardware power-loss validation or scaling
benchmark ran. Generic gate execution records local consumption only. Split is
explicitly unsupported. Direct database/bootstrap tampering is not a trusted identity
boundary. Keep the existing database and a verified checkpoint independently of source.
