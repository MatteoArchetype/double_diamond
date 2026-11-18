# Cycle 113 — fail-closed evidence ingestion

- Legacy boolean approval entry point now always rejects; callers must migrate to `ingest_with_review`.
- `ingest_with_review` requires an injected reviewer authorization callback, denying access by default.
- Review record digest is verified before use. The callback is a trust boundary supplied by the host, **not** a built-in identity provider.
- Batch ingestion stages changes in a deep-copied state, committing only if all documents succeed; in-memory atomicity only (no database transaction, crash durability, or concurrency isolation).
- Source snapshots are still caller-supplied and are **not** independently authenticated; approval does not establish source authenticity.
