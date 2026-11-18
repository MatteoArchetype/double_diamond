# Cycle 100 — Provider-neutral retrieval boundary

## Purpose
Add a strict boundary between retrieval and research reasoning without embedding a web/search provider.

## Change
`retrieval_adapter.py` introduces `RetrievedDocument` with:
- source identity, title and publisher
- URL and retrieval/publication timestamps
- bounded passage and exact content location
- provenance and explicit synthetic status
- independence cluster and extensible metadata

Conversion to an evidence payload does not create a claim, interpretation, hypothesis, or conclusion.

## Tests
Five new tests cover required metadata, URL validation, synthetic provenance,
non-interpretive conversion, and preservation of synthetic/independence metadata.

## Scope boundary
No network client, credentials, provider-specific retrieval implementation, or automatic claim generation is included.
