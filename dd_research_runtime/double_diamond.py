"""Versioned Double Diamond research visits with bounded, human-gated iteration."""
import copy
from .analysis_transactions import _keys,_text,_ids,_origin
from .persistent_ingestion import _encode,_checksum
from .gate_transactions import apply_gate

PHASES=('discover','define','develop','deliver')


def transition_action(state,to_phase,reason):
    from .workflow import domain_digest
    _text(reason,'reason')
    return dict(type='gated_action',action='phase_transition',payload=dict(workflow_id=state.workflow['workflow_id'],
        from_phase=state.workflow['phase'],to_phase=to_phase,reason=reason,research_digest=domain_digest(state)))


def reframing_action(state,record):
    from .workflow import domain_digest
    return dict(type='gated_action',action='material_reframing',payload=dict(workflow_id=state.workflow['workflow_id'],
        visit_id=state.workflow['visits'][-1]['visit_id'],record_digest=_checksum(_encode(record)),research_digest=domain_digest(state)))


def record_binding(state,phase,record):
    """Track referenced objects, avoiding false staleness from unrelated new research."""
    evidence=set(record.get('evidence_ids',[]));claims=set(record.get('claim_ids',[]));uncertainties=set(record.get('uncertainty_ids',[]))
    for item in record.get('alternatives',[]):
        evidence.update(item['evidence_ids']);claims.update(item['claim_ids'])
    for item in record.get('evaluations',[]):evidence.update(item['evidence_ids'])
    for cid in claims:
        evidence.update(state.claims[cid].get('evidence_ids',[]));uncertainties.update(state.claims[cid].get('material_uncertainties',[]))
    value=dict(phase=phase,record=record,brief=state.brief,scope=state.scope,questions=state.research_questions,
        claims={cid:state.claims[cid] for cid in sorted(claims)},evidence={eid:state.evidence[eid] for eid in sorted(evidence)},
        sources={state.evidence[eid]['source_id']:state.sources.get(state.evidence[eid]['source_id']) for eid in sorted(evidence)},
        uncertainties={uid:state.uncertainties[uid] for uid in sorted(uncertainties)})
    if phase=='deliver' and state.workflow.get('workflow_version')==3:
        value['defined_problem']=state.workflow['records']['define'];value['developed_alternatives']=state.workflow['records']['develop']
    return _checksum(_encode(value))


def stage_currency(state):
    return {phase:state.workflow['record_bindings'][phase]==record_binding(state,phase,record) for phase,record in state.workflow['records'].items()}


def _validate(state,phase,record):
    from .workflow import _refs
    if phase=='discover':
        _keys(record,{'evidence_ids','notes','perspectives','limitations'})
        _refs(state,record['evidence_ids'],'evidence','evidence_ids',True)
        _text(record['notes'],'notes');_text(record['limitations'],'limitations')
        _ids(record['perspectives'],'perspectives')
        if not 2<=len(record['perspectives'])<=20:raise ValueError('discover requires 2 to 20 stated perspectives, including known gaps')
    elif phase=='define':
        _keys(record,{'problem','claim_ids','uncertainty_ids','success_criteria'})
        _text(record['problem'],'problem');_refs(state,record['claim_ids'],'claims','claim_ids',True)
        _refs(state,record['uncertainty_ids'],'uncertainties','uncertainty_ids');_ids(record['success_criteria'],'success_criteria')
        if not 1<=len(record['success_criteria'])<=20:raise ValueError('define requires bounded success criteria')
    elif phase=='develop':
        _keys(record,{'alternatives'})
        items=record['alternatives']
        if not isinstance(items,list) or not 2<=len(items)<=state.workflow['max_alternatives']:raise ValueError('develop requires bounded competing alternatives')
        seen=set()
        for item in items:
            _keys(item,{'alternative_id','hypothesis','test','claim_ids','evidence_ids','limitations'})
            for name in ('alternative_id','hypothesis','test','limitations'):_text(item[name],name)
            if item['alternative_id'] in seen:raise ValueError('duplicate alternative ID')
            seen.add(item['alternative_id']);_refs(state,item['claim_ids'],'claims','claim_ids',True);_refs(state,item['evidence_ids'],'evidence','evidence_ids')
    elif phase=='deliver':
        required={'selected_alternative_id','evaluations','decision','summary','claim_ids','limitations'}
        if state.workflow.get('workflow_version')==3:required.add('criterion_assessments')
        _keys(record,required)
        for name in ('summary','limitations'):_text(record[name],name)
        _refs(state,record['claim_ids'],'claims','claim_ids',True)
        alternatives={a['alternative_id'] for a in state.workflow['records']['develop']['alternatives']}
        if record['selected_alternative_id'] not in alternatives:raise ValueError('select a current developed alternative')
        if record['decision'] not in {'recommend','revise','stop_unresolved'}:raise ValueError('invalid deliver decision')
        evaluations=record['evaluations'];seen=set()
        if not isinstance(evaluations,list) or not 1<=len(evaluations)<=20:raise ValueError('deliver requires 1 to 20 recorded evaluations')
        selected_support=False;selected_tested=False
        for item in evaluations:
            _keys(item,{'evaluation_id','alternative_id','method','evidence_ids','outcome','limitations'})
            for name in ('evaluation_id','method','limitations'):_text(item[name],name)
            if item['evaluation_id'] in seen or item['alternative_id'] not in alternatives:raise ValueError('duplicate evaluation or unknown alternative')
            seen.add(item['evaluation_id']);_refs(state,item['evidence_ids'],'evidence','evidence_ids')
            if item['outcome'] not in {'supported','unsupported','inconclusive'}:raise ValueError('invalid evaluation outcome')
            if item['outcome']!='inconclusive' and not item['evidence_ids']:raise ValueError('evaluation outcome requires evidence')
            if item['alternative_id']==record['selected_alternative_id']:
                selected_tested=True;selected_support |= item['outcome']=='supported'
        if not selected_tested:raise ValueError('selected alternative requires evaluation')
        if record['decision']=='recommend' and not selected_support:raise ValueError('recommendation requires recorded support for selected alternative')
        if state.workflow.get('workflow_version')==3:
            validate_criteria(state,record)
    else:raise ValueError('invalid Double Diamond phase')


def apply_double_diamond(state,command,*,actor,rationale,operation_id,timestamp):
    kind=command.get('type');workflow=getattr(state,'workflow',None);start=len(state.change_log)
    if kind in {'start_double_diamond','start_criteria_research'}:
        _keys(command,{'type','workflow_id','brief','scope','questions','max_alternatives','max_visits'})
        if workflow or state.brief or state.scope or state.research_questions:raise ValueError('new Double Diamond case requires empty workflow/brief/scope/questions')
        for name in ('workflow_id','brief','scope'):_text(command[name],name)
        _ids(command['questions'],'questions')
        if not 1<=len(command['questions'])<=20:raise ValueError('requires 1 to 20 questions')
        if type(command['max_alternatives']) is not int or not 2<=command['max_alternatives']<=20:raise ValueError('invalid alternative budget')
        if type(command['max_visits']) is not int or not 4<=command['max_visits']<=20:raise ValueError('visit budget must be 4 to 20')
        state.brief={'text':command['brief']};state.scope={'text':command['scope']}
        state.research_questions=[dict(question_id='Q'+str(i),question=q) for i,q in enumerate(command['questions'],1)]
        workflow=dict(workflow_id=command['workflow_id'],methodology='double_diamond',workflow_version=3 if kind=='start_criteria_research' else 2,phase='discover',status='active',
            max_alternatives=command['max_alternatives'],max_visits=command['max_visits'],records={},record_bindings={},history=[],
            visits=[dict(visit_id='V1',phase='discover',reason='Initial discovery',record=None,binding=None)])
        state.workflow=workflow
    elif kind=='record':
        _keys(command,{'type','phase','record'},{'gate_id'})
        phase=command['phase'];record=command['record'];visit=workflow['visits'][-1]
        if workflow['status']!='active' or phase!=workflow['phase']:raise ValueError('record must match active phase')
        if visit['record'] is not None:raise ValueError('visit record is immutable; revisit to revise')
        _validate(state,phase,record)
        prior=[v for v in workflow['visits'][:-1] if v['phase']=='define' and v['record'] is not None]
        reframing=phase=='define' and prior and prior[-1]['record']!=record
        if reframing:
            if 'gate_id' not in command:raise PermissionError('changed problem framing requires exact human approval')
            apply_gate(state,dict(type='execute',gate_id=command['gate_id'],action=reframing_action(state,record)),actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
        elif 'gate_id' in command:raise ValueError('reframing gate is only valid for a changed problem frame')
        binding=record_binding(state,phase,record)
        visit.update(record=copy.deepcopy(record),binding=binding,record_operation_id=operation_id)
        workflow['records'][phase]=copy.deepcopy(record);workflow['record_bindings'][phase]=binding
    elif kind in {'advance','revisit','reopen'}:
        _keys(command,{'type','to_phase','reason','gate_id'})
        target=command['to_phase'];current=workflow['phase'];_text(command['reason'],'reason')
        if target not in PHASES:raise ValueError('unknown Double Diamond phase')
        if len(workflow['visits'])>=workflow['max_visits']:raise ValueError('visit budget exhausted; stop or escalate')
        if kind=='reopen':
            if workflow['status']=='active':raise ValueError('reopen requires a terminal workflow')
        elif workflow['status']!='active':raise ValueError('terminal workflow requires an approved reopen')
        if kind=='advance':
            if current=='deliver' or target!=PHASES[PHASES.index(current)+1]:raise ValueError('advance requires the next phase')
            if current not in workflow['records'] or not stage_currency(state).get(current):raise ValueError('current phase record required; revisit stale findings')
        elif PHASES.index(target)>PHASES.index(current):raise ValueError('revisit/reopen must return to current or earlier phase')
        apply_gate(state,dict(type='execute',gate_id=command['gate_id'],action=transition_action(state,target,command['reason'])),actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
        # Supersede only current projections; immutable visits retain the original findings.
        for phase in PHASES[PHASES.index(target):]:
            workflow['records'].pop(phase,None);workflow['record_bindings'].pop(phase,None)
        workflow['history'].append(dict(kind=kind,from_phase=current,to_phase=target,reason=command['reason'],gate_id=command['gate_id'],operation_id=operation_id))
        workflow['visits'].append(dict(visit_id='V'+str(len(workflow['visits'])+1),phase=target,reason=command['reason'],record=None,binding=None))
        workflow.update(phase=target,status='active');workflow.pop('stopping_reason',None)
    elif kind=='finish':
        _keys(command,{'type','outcome','reason'});_text(command['reason'],'reason')
        if workflow['status']!='active' or command['outcome'] not in {'stopped','escalated'}:raise ValueError('invalid terminal decision')
        if command['outcome']=='stopped':
            if workflow['phase']!='deliver' or set(workflow['records'])!=set(PHASES) or not all(stage_currency(state).values()):raise ValueError('current complete Double Diamond research records required')
            if workflow['records']['deliver']['decision']=='revise':raise ValueError('revise requires iteration or escalation')
        workflow.update(status=command['outcome'],stopping_reason=command['reason'])
    elif kind=='report':
        _keys(command,{'type','report_id'},{'include_evaluation_evidence'});_text(command['report_id'],'report_id')
        include_evaluation_evidence=command.get('include_evaluation_evidence',False)
        if type(include_evaluation_evidence) is not bool:raise ValueError('invalid report evidence option')
        if workflow['status']=='active' or command['report_id'] in state.outputs:raise ValueError('terminal workflow and new report ID required')
        from .reporting import build_report
        state.outputs[command['report_id']]=build_report(state,report_id=command['report_id'],actor=actor,timestamp=timestamp,include_evaluation_evidence=include_evaluation_evidence)
    else:raise ValueError('unsupported Double Diamond operation')
    state._change('double_diamond_'+kind,[workflow['workflow_id']],dict(actor=actor,rationale=rationale,operation_id=operation_id))
    for item in state.change_log[start:]:item['timestamp']=timestamp
    return [command['report_id']] if kind=='report' else [workflow['workflow_id']]


def validate_criteria(state,record):
    """Check traceability and explicit gaps, never assert experimental validity."""
    criteria=state.workflow['records']['define']['success_criteria']
    assessments=record['criterion_assessments']
    if not isinstance(assessments,list) or len(assessments)!=len(criteria):raise ValueError('assess every current success criterion exactly once')
    evaluations={item['evaluation_id']:item for item in record['evaluations']};seen=set()
    for item in assessments:
        _keys(item,{'criterion_index','outcome','evaluation_ids','rationale','next_research'})
        index=item['criterion_index']
        if type(index) is not int or not 0<=index<len(criteria) or index in seen:raise ValueError('invalid or duplicate criterion index')
        seen.add(index);_text(item['rationale'],'rationale');_ids(item['evaluation_ids'],'evaluation_ids')
        if item['outcome'] not in {'met','not_met','unknown'}:raise ValueError('invalid criterion outcome')
        if not isinstance(item['next_research'],str):raise ValueError('next_research must be text')
        linked=[]
        for eid in item['evaluation_ids']:
            if eid not in evaluations:raise ValueError('unknown criterion evaluation')
            evaluation=evaluations[eid]
            if evaluation['alternative_id']!=record['selected_alternative_id']:raise ValueError('criterion must evaluate selected alternative')
            linked.append(evaluation)
        if item['outcome']!='unknown':
            required='supported' if item['outcome']=='met' else 'unsupported'
            if not any(e['outcome']==required and e['evidence_ids'] for e in linked):raise ValueError('criterion outcome needs matching evidence-backed evaluation')
        if item['outcome']!='met':_text(item['next_research'],'next_research')
    if record['decision']=='recommend' and any(a['outcome']!='met' for a in assessments):raise ValueError('recommendation requires all success criteria met')


def decision_trace(state):
    record=state.workflow['records'].get('deliver')
    if not record:return None
    evaluations={item['evaluation_id']:item for item in record['evaluations']}
    rows=[]
    for item in sorted(record['criterion_assessments'],key=lambda x:x['criterion_index']):
        linked=[evaluations[eid] for eid in item['evaluation_ids']]
        evidence=sorted({eid for e in linked for eid in e['evidence_ids']})
        rows.append(dict(criterion_index=item['criterion_index'],criterion=state.workflow['records']['define']['success_criteria'][item['criterion_index']],
            outcome=item['outcome'],rationale=item['rationale'],next_research=item['next_research'],evaluation_ids=item['evaluation_ids'],
            evidence_ids=evidence,evidence_origin=_origin(state,evidence)))
    return dict(selected_alternative_id=record['selected_alternative_id'],decision=record['decision'],criteria=rows,
                all_criteria_met=all(row['outcome']=='met' for row in rows),verification='host-recorded assessment; not independent experiment validation')
