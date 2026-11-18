"""Read-only navigation guidance. Never research execution, validation or permission."""
from .double_diamond import PHASES,stage_currency
from .reporting import report_is_current


def research_gate_contexts(state):
    """Read-only content match, not permission, approval or application readiness."""
    from .workflow import domain_digest
    digest=domain_digest(state)
    workflow=state.workflow
    result={}
    for gid,gate in state.human_gates.items():
        kind=gate.get('gate_type')
        if kind not in {'phase_transition','material_reframing'}:continue
        action=gate.get('action',{});payload=action.get('payload',{})
        result[gid]=(action.get('type')=='gated_action' and action.get('action')==kind
                     and payload.get('research_digest')==digest
                     and payload.get('workflow_id')==workflow['workflow_id']
                     and (payload.get('from_phase')==workflow['phase'] if kind=='phase_transition'
                          else payload.get('visit_id')==workflow['visits'][-1]['visit_id']))
    return result


def build_guidance(state,*,synthetic_example=False):
    workflow=getattr(state,'workflow',{})
    if workflow.get('workflow_version') not in {2,3}:raise ValueError('guided interface requires a Double Diamond case')
    phase=workflow['phase'];currency=stage_currency(state)
    records=workflow['records'];used=len(workflow['visits']);remaining=workflow['max_visits']-used
    contexts=research_gate_contexts(state)
    pending=[g for gid,g in state.human_gates.items() if contexts.get(gid) and g.get('status')=='pending_review']
    approved=[g for gid,g in state.human_gates.items() if contexts.get(gid) and g.get('status')=='approved']
    current_reports=[rid for rid,r in state.outputs.items() if 'content_digest' in r and report_is_current(state,rid)]
    synthetic=sum(e.get('synthetic') is True for e in state.evidence.values())
    result=dict(advisory_only=True,execution_authorized=False,synthetic_example=synthetic_example,
        phase=phase,status=workflow['status'],visits_used=used,visits_remaining=remaining,
        research_reviews_pending=len(pending),approved_changes_unapplied=len(approved),
        outdated_research_reviews=sum(not contexts[gid] and g.get('status') in {'pending_review','approved'} for gid,g in state.human_gates.items() if gid in contexts),
        evidence_counts=dict(synthetic=synthetic,source_records=len(state.evidence)-synthetic),
        phases=[dict(phase=p,status='needs_review' if p in records and not currency[p] else 'saved' if p in records else 'not_recorded') for p in PHASES],
        current_report_count=len(current_reports),
        budget_note='No further phase visits remain. You may finish the current visit if its requirements allow, then stop or escalate.' if remaining==0 else 'Returning to Define and reassessing Develop and Deliver needs three phase visits.',
        boundary='Navigation guidance only. Source review, phase changes, frame approval, final acceptance and external actions remain separate decisions.')
    def step(code,title,detail,tab,label):
        result.update(step=code,title=title,detail=detail,navigation=dict(tab=tab,label=label));return result
    if pending:
        return step('review_pending','A saved research change needs review',
            'Inspect the exact proposed change and approve or reject it. A proposal does not change the research; approval and application are separate. Older proposals may be stale.',
            'Approvals','Review saved proposals')
    if approved:
        return step('apply_separately','An approved research change is awaiting application',
            'Review the saved approval before explicitly applying it. Approval alone has not moved the phase or recorded the revised frame. Stale changes will be refused.',
            'Approvals','Inspect approved changes')
    if any(not value for value in currency.values()):
        return step('review_changed_basis','Some saved findings need review',
            'Referenced research has changed. Inspect the affected phase and its original evidence, then request a reviewed return before relying on it for a new conclusion.',
            'Research','Inspect saved research')
    if workflow['status']!='active':
        if current_reports:
            return step('inspect_report','This research pass has a saved draft',
                'Read the findings, evidence, limits and unresolved criteria. A saved draft is not publication approval or proof that an explanation has been validated.',
                'Reports','Inspect research drafts')
        return step('prepare_report','This research pass is '+workflow['status'],
            'Review what was recorded and save a readable draft if useful. An incomplete escalated pass must keep its missing evidence and findings explicit.',
            'Reports','Review report options')
    if phase not in records:
        if phase=='discover' and not state.evidence:
            return step('review_source','Discover starts with reviewed evidence',
                'Add a source passage, its exact location and independently acquired source text. Check its context and explicitly approve intake. Mark invented material as synthetic.',
                'Sources','Open source review')
        if phase=='define' and not state.claims:
            return step('record_interpretation','Define needs a working interpretation',
                'Record an advisory interpretation and its evidence links before framing the problem. An interpretation is not a confirmed fact.',
                'Interpretations','Open interpretations')
        instructions={
            'discover':('Explore perspectives and gaps','Record what you observed, which perspectives are represented, which are missing, and the limits of the evidence.'),
            'define':('Frame a bounded problem','State the problem and success criteria. Choose relevant interpretations and uncertainties explicitly. If revising an earlier frame, review it before copying.'),
            'develop':('Compare competing alternatives','Record at least two alternatives, proposed tests and assumptions. A proposed test is not a completed evaluation.'),
            'deliver':('Evaluate against the defined criteria','Record an evaluation actually carried out, its evidence and limits, and assess every success criterion. Failed or unknown criteria need next research.')}
        title,detail=instructions[phase]
        return step('record_'+phase,title,detail,'Research','Open '+phase.capitalize()+' work')
    if phase=='deliver':
        if records[phase]['decision']=='revise':
            return step('return_for_revision','The recorded decision is to revise',
                'Request a reviewed return to an earlier phase, or escalate if the remaining budget or evidence prevents another pass. Do not treat a revision decision as a completed result.',
                'Research','Review return or escalation')
        return step('finish_or_return','Review whether this pass should stop or return',
            'Inspect the criterion assessments and limits. Explicitly finish a bounded pass, request a reviewed return, or escalate. No recommendation is independently validated by this guidance.',
            'Research','Review the research decision')
    if remaining==0:
        return step('budget_exhausted','The phase-visit budget is exhausted',
            'Your saved findings remain available. The limit cannot be expanded by navigation guidance. Escalate incomplete work; finishing still requires the recorded workflow conditions.',
            'Research','Review stop or escalation')
    return step('review_transition',phase.capitalize()+' findings are saved',
        'Inspect the saved finding and its limitations, then explicitly request review for the next phase or a return. Viewing a phase does not move the research.',
        'Research','Review the next phase decision')
