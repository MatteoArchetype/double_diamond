# Run the current fixture and inspect MVP gaps

Use Python 3.10 or later from this cycle's source directory. No network access,
external account or pytest dependency is needed for the demo itself.

```sh
python3 -m dd_research_runtime.mvp_demo
```

By default all fixture databases and checkpoint files are temporary and cleaned on
normal completion. The JSON report goes to stdout. It labels the run fixture-only,
shows the observed checks and acceptance backlog, and currently reports mvp_ready=false.
Exit 0 means the implemented fixture invariants passed, not that the MVP is complete.

To keep the fixture files explicitly in a new directory:

```sh
python3 -m dd_research_runtime.mvp_demo --keep /path/to/new-fixture-directory
```

The parent directory must already exist. Existing directories are refused without
overwriting them. Kept files include fixture.sqlite, fixture-checkpoint.zip,
restored.sqlite and demo-report.json. All data is synthetic example material, not
real participants or research evidence. Failure may leave a partial kept fixture
run for inspection; no cleanup is attempted on an existing user directory.

The demo uses a named fixture reviewer and an authorization callback stub. This is
not real identity authentication or independent source acquisition. A host acceptance
case must use real host controls and independently obtained source snapshots.

The workflow prepares retrieval, saves/reopens review, checks permission, ingests only
the explicitly synthetic fixture and retains its review/snapshot. It then writes durable
advisory claims, assessment, contradiction, uncertainty and disposition through the new
analysis API, retries evidence ingestion without duplication, preserves the pending
publication gate and restores a checkpoint. Direct edits to loaded objects remain
detached; use apply_analysis for supported durable changes. Gate decisions remain future
work. Assessment freshness is checked against the final qualified claim version.

MVP_ACCEPTANCE.json and MVP_BACKLOG.md define the stopping criteria and targeted
remaining cycles. MVP_FIXTURE_RESULTS.json records an actual run for this release;
it is not a real-source acceptance report. Run the demo again to verify your copy.

Cycle 129 also persists a simulated phase-transition proposal, approval and local consumption, checks exact authorization and retry, and restores those gate records. The publication gate remains pending. Generic consumption performs no external work.

Cycle 130 extends the fixture through discovery, definition, two inconclusive alternative comparisons, synthesis and an explicit stop. Four durable human transition decisions are simulated. research-draft.md and research-draft.json retain source passages, synthetic labels, uncertainty and pending publication status. See WORKFLOW_GUIDE.md for APIs and export commands.

Cycle 131 additionally checks that this synthetic-only demo cannot satisfy host real-source acceptance. Use the separate acceptance_cli prepare-public command for the real-source candidate; it creates a pending handoff, not an approved study.
