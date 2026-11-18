# Cycle 112 — Snapshot-bound evidence review

Added `dd_research_runtime/evidence_review.py` with exact passage-in-snapshot matching, exact locator matching, source snapshot digests, batch-bound review digests, duplicate detection (within batch and against state), and a review-gated ingestion entrypoint.

Security and epistemic limitations:
- Snapshots are caller-supplied and not independently fetched or cryptographically authenticated by the runtime. A dishonest executor could supply matching fabricated text. Snapshot verification therefore establishes internal consistency, not source authenticity.
- Reviewer identity is a nonempty string, not authenticated authorization.
- Existing legacy `ingest_reviewed_retrieval(approved=True)` remains available and bypasses Cycle 112's stronger review path. It must be deprecated or restricted before production.
- Multi-document state writes are not transactional; unexpected state write failures can leave partial mutations. Preflight reduces known failures but does not guarantee atomicity.
- No real web retrieval, persistent audit database, or production identity provider.

Cycle 113 priorities: eliminate legacy bypass, transactional batch ingestion, authenticate review and bind snapshot to trusted retrieval provenance.
