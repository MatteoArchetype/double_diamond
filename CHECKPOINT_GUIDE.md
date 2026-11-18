# Verify, back up and restore a research database

Run these commands from this cycle's source directory using Python 3.10 or later.
The checkpoint commands use the standard library; pytest is needed only for tests.
Replace the example database and output paths with your own paths. No database is
created or initialized merely by running help or verification.

```sh
python3 -m dd_research_runtime.checkpoint_cli --help
python3 -m dd_research_runtime.checkpoint_cli verify research.db --pretty
python3 -m dd_research_runtime.checkpoint_cli create research.db research-backup.zip
python3 -m dd_research_runtime.checkpoint_cli inspect research-backup.zip --pretty
python3 -m dd_research_runtime.checkpoint_cli restore research-backup.zip restored-research.db
```

The source database must already exist and have the supported runtime schema.
Verification and backup creation open it read-only, without store initialization,
migration or repair. Older databases may require explicit adoption through the
runtime's library APIs before checkpointing; the commands do not infer or perform it.

A cycle ZIP contains application source code. A database checkpoint ZIP contains
research.sqlite and manifest.json. They are different artifacts and are not
interchangeable. Creating a cycle source ZIP does not back up your research database.

Outputs are JSON by default. --pretty changes indentation only. Successful reports
include verified counts and hashes, not source passages, review bodies or rationale.
They do not claim source authenticity or reviewer identity. Error messages can include
paths and integrity details; filesystem access controls still apply.

Exit codes:

- 0: success. --help also exits 0, with ordinary help text.
- 1: operational failure, with JSON error details on stderr.
- 2: usage error, with JSON error details on stderr.
- 130: caught interruption. An already published destination may still be complete.

Success JSON is written to stdout; failures use stderr with a stable error code
such as destination_exists, not_found, invalid_data, permission_denied or io_error.
Some SQLite access failures surface as invalid_data rather than an OS permission error.

Destinations must be new paths with existing parent directories. There is no --force
or overwrite mode. After an interruption or output/connection failure, inspect a
checkpoint that already exists before retrying. Do not delete or replace it merely
because the command did not return a success message.

Checkpoints contain plaintext state, source snapshots and audit records. Published
files are owner-readable/writable, but are not encrypted or signed. Normal failures
clean staging; process death can leave private staging directories. This cycle does
not upload, schedule or automatically clean backups. See CYCLE_125.md and CYCLE_126.md
for filesystem and recovery limitations.
