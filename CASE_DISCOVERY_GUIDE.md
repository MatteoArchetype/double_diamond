# When a saved case cannot be opened

The workspace now inspects saved case databases read-only, without invoking constructors,
initialization, adoption, migration or repair. Healthy supported Double Diamond cases are
listed as before. A separate notice names candidate cases that cannot currently be verified
or opened. Their files are left unchanged; other cases remain available.

The notice does not diagnose a specific cause: missing/incomplete database or metadata,
invalid records, an unsupported earlier workflow, a file access issue or a transient lock
may make a case unavailable. It does not claim corruption is the only explanation.
Keep original files for inspection. A trusted checkpoint can be restored as a separate
case using Restore a backup. That retains history and does not renew human approval.
Earlier unsupported formats may require the existing library/checkpoint tools.

Private staging directories and empty reservations from interrupted creation are not
listed as saved research. Case file symlinks are refused rather than followed. Unavailable
records are not automatically repaired, deleted, migrated, adopted or overwritten.

Discovery is not an atomic snapshot of every case at once: it verifies one database at a
time. A concurrently published case may appear on the next refresh, and a temporarily
unreadable case can be retried. Case opening and saved-report downloads now use the same constructor-free read-only
verification. Case opening also validates metadata and refuses metadata symlinks. The
existing explicit library write/adoption APIs are unchanged.

The authenticated /api/cases route retains its healthy-case list shape. /api/catalog
adds unavailable-case summaries for the browser without exposing raw filesystem/SQL errors.
Source integrity, synthetic distinction and Double Diamond human gates are unchanged.
No source authentication, new approval, actual research or final MVP-08 acceptance is
inferred from a case appearing in the list. Test fixtures are invented material only.

Incomplete files reached through an old direct case/report link are refused without creating tables. Supported pre-journal records stay pre-journal during inspection; missing history is not invented or adopted. Saved report wording is rendered from its retained output snapshot, not rewritten from current interpretations.
