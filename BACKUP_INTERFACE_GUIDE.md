# Saved-work backup and restore

In a case, open **Backups**, then **Download case checkpoint**. The checkpoint contains
saved research, source snapshots, audit history and historical decisions for that case.
Unsaved fields and other cases are excluded. Keep this plaintext ZIP privately. Code
release archives do not back up research data.

Choose **Restore a backup**, select a trusted checkpoint and inspect it. Review the title,
phase, source/synthetic counts and historical decision counts. Inspection verifies the
archive and replay journal; it does not authenticate the source or historical reviewer.
Confirm a separate copy explicitly. Existing cases are never overwritten. Historical
approvals are preserved as records, not renewed or converted into fresh approvals.

Browser transfers are limited to 32 MiB and workflow version 3 (criterion-linked Double
Diamond). Earlier workflow formats and larger cases use CHECKPOINT_GUIDE.md. No automatic
format migration or scheduled/remote backup is added. A stale download request must be
refreshed. Changing the selected file requires inspection again.

A restore interrupted before publication exposes no usable partial case. After publication,
a complete case remains even if the response is lost. Reopen Your research before retrying:
a deliberate repeat creates another separate copy, with no exactly-once retry guarantee.
A hard process stop can leave hidden staging files or an empty reserved directory, ignored
by the case list. Automated cleanup of crash remnants is not provided. Normal failures
clean up their own unpublished empty reservations. Filesystem replacement is verified on
this Mac only; no hardware-power-loss, hostile local-user or cross-platform guarantee.

The local interface remains single operator. A checkpoint preserves source labels, evidence,
phase findings and gate status; restoring is not a Double Diamond phase transition, research
validation, final acceptance, publication approval or permission to execute external work.
