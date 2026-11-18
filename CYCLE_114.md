# Cycle 114 — Persistent review audit receipts

Adds `dd_research_runtime.review_ledger.ReviewLedger`: SQLite append-only receipts, hash chaining, integrity verification, unique review digest and optimistic concurrency via `expected_revision` with `BEGIN IMMEDIATE`. Tests include persistence, tamper detection, stale revisions, duplicates and rejected-review recording.

**Limits:** This is tamper-evident only against accidental/partial modification, not a cryptographically signed or externally anchored immutable log. It does not authenticate reviewers, validate source authenticity, or transactionally commit the separate in-memory research state. Existing evidence ingestion is unchanged. Integrate authenticated identities and an atomic state+ledger commit in a future cycle.
