# Your local Double Diamond workspace

Cycle 152 extends the first browser interface for a single operator. Python 3.10 or later
is required; no web framework, package installation or internet connection is needed.

On macOS, open **Start Research.command** in this folder. Keep its terminal open,
then open the private local link it prints in your browser. Stop with Control+C.
If Finder blocks the launcher, open Terminal in this folder and run:

```
python3 -m dd_research_runtime.local_app --workspace research-workspace
```

To create a clearly labelled synthetic learning case, use Create synthetic learning example
on the welcome screen or new-case form. The `--demo` launch option also remains available.
Each deliberate request creates another example; no real research is inferred. Existing cases are retained in the workspace you select.
The server listens only on 127.0.0.1, chooses an available port, and requires a fresh
private launch key for research access. Treat that link as access to your workspace.
Nothing is published. No analytics, external fonts or remote scripts are loaded.

The Where you are panel offers navigation based on the saved case, with record statuses
and remaining visits. Its guidance does not save, approve or execute anything. See
FIRST_RUN_GUIDE.md for the first-run walkthrough.

## Work through the Double Diamond

1. Create a case with a research question, boundaries and a visit budget.
2. In Sources, retain an exact passage, locator and separately acquired source text.
   Check the original context, label synthetic material, and explicitly approve intake.
   The tool checks passage containment; it cannot prove your independent acquisition,
   the source's truth, completeness or independence.
3. In Interpretations, connect advisory working interpretations to evidence. Record open
   questions separately and link them explicitly; select relevant uncertainties in Define.
4. Discover: record evidence, observations, different perspectives and missing voices.
5. Define: frame the problem and state what would count as success.
6. Develop: describe at least two competing alternatives, each with separately selected
   interpretations/passages, a proposed test and limits. New rows inherit no links.
7. Deliver: record an evaluation actually carried out, evidence, limits and an explicit
   assessment of every success criterion. Unknown or failed criteria require next research.
8. Request a phase change, then separately review it in Approvals and apply the exact
   approved change. Returning to Define with a changed frame needs another exact review.
   Research history is retained; a later return does not rewrite an earlier visit.
9. Finish a supported, bounded pass or escalate incomplete work. Save and download a
   readable draft in Reports. Next research turns unmet criteria into proposed questions,
   methods, priorities and dependencies. Plans remain unexecuted proposals.

Click a phase to inspect its latest visit, or inspect an earlier visit from Research history. The saved view shows complete findings and their original evidence/interpretation context. Inspection does not change the phase or approve anything. Return to current research to continue. See VISIT_REVIEW_GUIDE.md for historical-context limits.

When returning to Define, you can review the earlier saved frame and explicitly copy it into an unsaved form. Check current links, choose uncertainties and enter a fresh saving reason. Changed frames still require separate review and application. See FRAME_REVISION_GUIDE.md.

Save each phase before progressing. A changed browser revision is refused; refresh,
review the current research and deliberately resubmit. An uncertain response is not
silently retried. Check saved state before repeating an action. Unsaved fields survive
section switching within the current case revision but are not saved across refreshes,
closing the page or changes to the case. Do not treat an unsaved form as a backup.

## Boundaries of this first interface

- One local operator; launch-key access is not independent identity verification,
  role separation, a hosted service or a security boundary against other local users.
- Manual source entry and interpretation. No automated retrieval, participant contact,
  experiments, publishing or final MVP acceptance controls.
- Develop uses per-alternative interpretation/evidence links; Deliver supports 1–20
  separate evaluations with criterion-specific links. Editing uncertainty/disagreement
  lifecycles and broader analysis remain limited.
- Existing legacy databases are not imported or migrated by this interface. The earlier
  public-source acceptance candidate and its pending human gates remain untouched.
- Source fidelity and durable audit history do not validate a study design or establish
  causal conclusions. This interface has not yet been accepted through a real user study.
- Back up research separately using the documented checkpoint tools. Release ZIPs contain
  code and synthetic fixtures, not your local research workspace or a data backup.

See DOUBLE_DIAMOND_GUIDE.md, CRITERIA_GUIDE.md, CHECKPOINT_GUIDE.md and
ACCEPTANCE_GUIDE.md for the underlying method, storage and human acceptance boundaries.

Cycle 139: use the Backups section or Restore a backup for saved-work recovery. See [BACKUP_INTERFACE_GUIDE.md](BACKUP_INTERFACE_GUIDE.md) for limits and the separate-copy confirmation flow.

Cycle 140 closes the single-evaluation Deliver form gap. See DELIVER_EVALUATIONS_GUIDE.md for explicit evidence links, removing rows and unsaved-draft limits.

Cycle 141: record open research questions and explicit interpretation links in Interpretations. See [UNCERTAINTY_INTERFACE_GUIDE.md](UNCERTAINTY_INTERFACE_GUIDE.md).

Cycle 142: record unresolved disagreements in Interpretations and inspect their retained report versions. See DISAGREEMENT_INTERFACE_GUIDE.md.

Cycle 143: Evidence fit records advisory qualitative assessments of an explicitly linked interpretation and passage. See EVIDENCE_FIT_INTERFACE_GUIDE.md for defaults, freshness and report-time context.

Cycle 144: Develop keeps each alternative’s evidence and interpretations separate. See DEVELOP_ALTERNATIVES_GUIDE.md.

Cycle 145: eligible advisory draft interpretations can be revised with earlier versions retained. Decision records remain in their host workflow. See ADVISORY_REVISION_GUIDE.md.

New empty-case and synthetic learning-example creation publish complete staged cases. If a response is uncertain, inspect Your research before creating again. See CASE_CREATION_RECOVERY.md; creation is not exactly-once across separate user requests.

If a saved case cannot be opened, the interface names it and preserves its files. Other verified cases remain available. See CASE_DISCOVERY_GUIDE.md; listing does not repair or migrate research.

Opening case state and downloading saved reports also use read-only verification. These actions do not implicitly initialize, adopt, migrate or repair database files.
