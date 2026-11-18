# Cycle 123 — Strict retrieval types and synthetic classification

## Starting point

Continues verified Cycle 122 archive SHA-256
`e66e33290f9cadaf21bc33b0ce049d4f50c6f2ec2e761c48a6f27e77ba623f7b`.
The unchanged baseline passed **408 tests in 5.72s** before implementation.

## Problem and behavior

RetrievedDocument previously tested required values through str(value), allowing
None, numbers and containers to appear nonempty. Synthetic classification used
truthiness, so values such as the string "false" could be treated as synthetic.
A reserved synthetic provenance label could also be paired with synthetic=False.
Malformed metadata could survive structural validation and fail only at persistence.

Cycle 123 tightens the provider-neutral retrieval boundary:

- Required source ID, title, publisher, URL, retrieval date, passage, location and
  provenance fields must be nonblank strings. Values are not implicitly stringified.
- synthetic must be an actual bool. Strings, numbers, None and collections fail.
- Reserved synthetic provenance labels synthetic, synthetic_test and synthetic-test
  require synthetic=True; synthetic=True also requires one of those labels. Label
  comparison ignores case and surrounding whitespace, while the original value is
  preserved in the payload. No synthetic evidence is promoted to a real source.
- Optional published_at and independence_cluster must be nonblank strings or None.
  Existing ingestion still requires a real source's independence cluster.
- Metadata must be a mapping with string keys and finite JSON values: strings,
  booleans, integers, finite floats, null, lists and nested mappings. Unsupported
  Python objects, tuples, sets, nonfinite floats, cycles and traversal beyond 100
  levels fail explicitly. Nested mappings are copied to plain JSON dictionaries.
- Conversion returns detached nested metadata. Shared input containers are allowed;
  they are not mistaken for cycles, and changing output does not mutate source data.

review_retrieval now validates each document before inspecting its snapshot, so a
manually constructed ready_for_review wrapper cannot bypass field checks. Conversion
also revalidates documents, protecting ingestion against mutable metadata altered
after review. Existing all-or-nothing batch rejection remains in effect.

No changes approve human gates, authenticate a reviewer, acquire sources, create
new evidence automatically, or change the persistent transaction boundary.

## Compatibility

Valid existing examples, legacy database fixtures, ordinary/context-bound review
hashes, snapshot retention and all earlier recovery/queue tests continue to pass.
Passage and exact locator strings are preserved verbatim; they are not trimmed or
rewritten. No new date parsing or source-identity assumptions are introduced.

This intentionally rejects some inputs earlier versions accepted. Hosts must supply
actual booleans, meaningful strings and JSON-compatible metadata; they must not use
coercion to hide ambiguity. Queued candidates are revalidated when read and may fail
closed if older malformed inputs were saved. This cycle does not silently rewrite
old candidates, infer synthetic status, recompute their approvals or repair history.

## Verification

See TEST_RESULTS.md for exact results. Added cases cover malformed required/optional
fields, synthetic truthiness, both provenance mismatch directions, JSON/cycle/depth
validation, nonfinite numbers, all-or-nothing batch rejection, manual-wrapper bypass,
post-review metadata mutation, nested copy isolation, faithful durable roundtrip and
direct reviewed-ingestion rejection without state changes.

## Limits and next work

- Strict shape and synthetic labels do not establish source truth or authenticity.
  Reserved label matching is not a semantic detector for every possible synthetic
  description. Host source acquisition and authenticated review remain necessary.
- Date fields remain nonblank strings, not verified timestamps. URL checks remain
  structural HTTP(S) checks; validation does not fetch or authenticate a URL.
- This hardens the provider-neutral RetrievedDocument/executor review path. Lower-
  level ResearchState and the separate legacy adapters remain host-controlled APIs;
  this is not a universal schema migration or reclassification of archived evidence.
- Archived payloads already committed by earlier versions are not retroactively
  rewritten. Invalid older pending candidates can require explicit investigation.
- Metadata depth is bounded, but source text and total payload size are not. No
  performance benchmark, live-source, identity-provider, hardware power-loss,
  disk-failure or other-platform verification was added.
- External retrieval-before-save recovery, exactly-once external work, scheduling
  and general durable claim/gate editing remain outside this cycle.
