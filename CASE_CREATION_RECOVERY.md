# Recovery when creating an empty research case

A new empty case starts in Discover, with its bounded brief and scope. Creation does not
add evidence, interpretations, findings or human decisions. For empty cases and synthetic learning examples, the database and case metadata
are prepared in a private staging directory, verified, then published together to a fresh,
exclusively reserved case identifier. An existing case is never overwritten.

Ordinary errors before publication clean up that attempt. After a hard process exit,
private .create- or .example- staging files or an empty reserved case folder may remain; the case list
ignores them. They are not automatically adopted or deleted. Existing cases stay available.
Restarting allows a new creation attempt without using those remnants.

If publication succeeded but its response was lost, a complete Discover case remains.
Inspect Your research before creating again. A second deliberate creation is a separate
case; this does not provide exactly-once creation across requests or a deduplication key.

Synthetic learning-example creation now uses the same reservation/publication boundary,
after its example builder finishes and its database and synthetic fixture result are
verified. A result claiming live sources, real acceptance or non-synthetic evidence is
refused. Checkpoint restore retains its own staging/publication boundary. No real research, source review, phase approval,
framing decision, publication or final acceptance is inferred from creation.

Tests simulate exceptions, abrupt process exits and concurrent creations. They do not
establish hardware power-loss durability, independent identity/source authentication,
cross-platform filesystem behavior or final MVP-08 acceptance.
