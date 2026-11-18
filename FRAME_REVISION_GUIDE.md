# Return to Define and revise a saved frame

When evidence changes your understanding, request a return to Define. Review that
phase-change proposal, approve or reject it, then separately apply an approved change.
The old findings remain in Research history. Inspecting a phase does not move it.
Check the visit budget before planning another pass: a return to Define plus renewed
Develop and Deliver needs three remaining visits. An exhausted budget requires stopping
or escalation; copying never expands it.

In an open Define visit:

1. Choose **Review previous saved frame**, or inspect an earlier Define visit from history.
2. Review its original problem, criteria, interpretations, evidence and uncertainties.
3. Choose **Replace current Define form with this frame**. This explicitly replaces any
   unsaved Define form. It only copies an editable draft; no finding or approval is saved.
4. Check the current interpretations and explicitly select the uncertainties to include.
   Unselected uncertainties are not silently added. Enter a fresh saving reason.
5. Save the draft. A changed frame becomes a proposal, showing the previous/proposed
   problem, criteria and changed sections. You can inspect the preceding saved frame.
6. Separately approve or reject the exact revised content. Approval alone does not apply
   it. Apply the approved change to record the new Define finding.
7. Reassess Develop and Deliver through their reviewed transitions before producing a
   current report. Earlier reports remain available and are marked historical/stale.

An unchanged frame may be recorded in the already-reviewed new Define visit without a
new material-reframing gate. It still needs an explicit save and fresh reason. Earlier
approvals are not copied. Changing criteria, interpretations or linked uncertainties
counts as a frame change just as changing the problem does.

## Reopening and limits

Saved proposals, decisions and findings survive closing/reopening the workspace and
checkpoint restore. An open Define visit shows a Continue saved frame review notice
when a saved proposal or approved frame still needs attention. An unsaved copied form is browser memory only; a page reload or
closing the browser loses it. A changed case revision is refused; inspect current saved
research before resubmitting. Copying cannot progress a phase or execute external work.

Copy is available only for an open, active Define visit and a saved earlier Define frame
with verified original journal context. Legacy/bootstrap records without original context
remain inspectable, but copy is refused; write a fresh draft rather than invent lineage.
No sources, claims, receipts, gates or reports are changed by copying.

This release does not add autosaved drafts, multi-user identity verification, independent
source acquisition, broader analysis editing, multiple Deliver evaluations in the form,
external research execution, publication or final acceptance. Those boundaries remain.

The library helper is read-only:

```
from dd_research_runtime.frame_revision import read_frame_draft
copy = read_frame_draft('/absolute/path/research.sqlite', 'V2', expected_revision=17)
```

It returns detached record data with `persisted=false` and `approval_granted=false`.
Saving remains a separate, revision-checked workflow action; it is never implied by GET.
