# Cycle 139 — browser checkpoint recovery

Built from unchanged Cycle 138: 936 tests passed in 87.85s. Adds saved-case checkpoint
download pinned to the displayed revision, inspection before confirmation, and restoration
as a separately identified case. Existing core checkpoint validation and replay verification
are reused. Source records and synthetic distinctions survive unchanged. Gate history and
pending decisions remain records; restoration never grants new approvals.

Uploads require the private launch token, exact local Host/Origin, bounded raw ZIP framing
and an inspected file digest. Publication reserves a fresh case directory exclusively and
atomically replaces only its own empty reservation with a verified database and metadata.
Failures before publication leave no usable partial case; failures after publication retain
the complete copy. Concurrent explicit restores produce separate complete copies.

See BACKUP_INTERFACE_GUIDE.md for the 32 MiB/browser workflow version 3 boundary, plaintext
storage, interrupted-response handling and crash-remnant limitations. Full acceptance of
research remains pending; actual research cases are untouched. No additional research gate,
external action, schema migration, independent identity provider or hosted service is added.
