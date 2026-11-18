"""Bounded local research workflow. All interpretations remain advisory."""
import copy
from .analysis_transactions import _keys, _text, _ids
from .persistent_ingestion import _encode, _checksum
from .gate_transactions import apply_gate

PHASES=('brief','discovery','definition','alternatives','synthesis')


def domain_digest(state):
    """Bind transitions to research content, independent of gate bookkeeping."""
    return _checksum(_encode({k:v for k,v in state.snapshot().items() if k not in {'human_gates','change_log','outputs','acceptance_records','research_agendas'}}))


def research_content_digest(state):
    return _checksum(_encode({k:v for k,v in state.snapshot().items() if k not in {'workflow','human_gates','change_log','outputs','acceptance_records','research_agendas'}}))


def transition_action(state, to_phase):
    workflow=getattr(state,'workflow',None)
    if not workflow:raise ValueError('workflow not started')
    return dict(type='gated_action',action='phase_transition',payload=dict(
        workflow_id=workflow['workflow_id'],from_phase=workflow['phase'],to_phase=to_phase,
        research_digest=domain_digest(state)))


def _refs(state,ids,collection,name,nonempty=False):
    _ids(ids,name)
    if nonempty and not ids:raise ValueError(name+' must not be empty')
    if any(i not in getattr(state,collection) for i in ids):raise ValueError('unknown '+name)


def apply_workflow(state,command,*,actor,rationale,operation_id,timestamp):
    _text(actor,'actor');_text(rationale,'rationale')
    if not isinstance(command,dict):raise ValueError('workflow command must be an object')
    kind=command.get('type');start=len(state.change_log)
    workflow=getattr(state,'workflow',None)
    if kind=='plan_research':
        from .research_agenda import apply_agenda
        return apply_agenda(state,command,actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
    if kind in {'start_double_diamond','start_criteria_research'} or (workflow and workflow.get('workflow_version') in {2,3}):
        from .double_diamond import apply_double_diamond
        return apply_double_diamond(state,command,actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
    if kind=='start':
        _keys(command,{'type','workflow_id','brief','scope','questions','max_alternatives'})
        if workflow:raise ValueError('workflow already started')
        for name in ('workflow_id','brief','scope'):_text(command[name],name)
        _ids(command['questions'],'questions')
        if not 1<=len(command['questions'])<=20:raise ValueError('requires 1 to 20 questions')
        if type(command['max_alternatives']) is not int or not 2<=command['max_alternatives']<=20:raise ValueError('max_alternatives must be 2 to 20')
        if state.brief or state.scope or state.research_questions:raise ValueError('existing brief/scope/questions require explicit migration')
        state.brief={'text':command['brief']};state.scope={'text':command['scope']}
        state.research_questions=[dict(question_id='Q'+str(i),question=q) for i,q in enumerate(command['questions'],1)]
        state.workflow=dict(workflow_id=command['workflow_id'],phase='brief',max_alternatives=command['max_alternatives'],records={},record_bindings={},history=[],status='active')
        workflow=state.workflow
    elif not workflow:raise ValueError('workflow not started')
    elif kind=='record':
        _keys(command,{'type','phase','record'})
        phase=command['phase'];record=command['record']
        if workflow['status']!='active' or phase!=workflow['phase'] or phase=='brief':raise ValueError('record must match active research phase')
        if phase in workflow['records']:raise ValueError('phase already recorded; corrections require a new bounded case')
        if phase=='discovery':
            _keys(record,{'evidence_ids','notes'})
            _refs(state,record['evidence_ids'],'evidence','evidence_ids',True);_text(record['notes'],'notes')
        elif phase=='definition':
            _keys(record,{'problem','claim_ids','uncertainty_ids'})
            _text(record['problem'],'problem');_refs(state,record['claim_ids'],'claims','claim_ids',True)
            _refs(state,record['uncertainty_ids'],'uncertainties','uncertainty_ids')
        elif phase=='alternatives':
            _keys(record,{'alternatives'})
            alternatives=record['alternatives']
            if not isinstance(alternatives,list) or not 2<=len(alternatives)<=workflow['max_alternatives']:raise ValueError('requires 2 to max_alternatives alternatives')
            seen=set()
            for item in alternatives:
                _keys(item,{'alternative_id','hypothesis','test','outcome','claim_ids','evidence_ids','limitations'})
                for name in ('alternative_id','hypothesis','test','limitations'):_text(item[name],name)
                if item['alternative_id'] in seen:raise ValueError('duplicate alternative ID')
                seen.add(item['alternative_id'])
                if item['outcome'] not in {'supported','unsupported','inconclusive'}:raise ValueError('invalid test outcome')
                _refs(state,item['claim_ids'],'claims','claim_ids',True);_refs(state,item['evidence_ids'],'evidence','evidence_ids')
                if item['outcome']!='inconclusive' and not item['evidence_ids']:raise ValueError('supported/unsupported tests require evidence')
        elif phase=='synthesis':
            _keys(record,{'summary','claim_ids','limitations'})
            _text(record['summary'],'summary');_text(record['limitations'],'limitations')
            _refs(state,record['claim_ids'],'claims','claim_ids',True)
        else:raise ValueError('unsupported phase')
        workflow['records'][phase]=copy.deepcopy(record)
        workflow['record_bindings'][phase]=research_content_digest(state)
    elif kind=='advance':
        _keys(command,{'type','to_phase','gate_id'})
        if workflow['status']!='active':raise ValueError('workflow is terminal')
        current=workflow['phase'];target=command['to_phase']
        if current not in PHASES or current=='synthesis' or target!=PHASES[PHASES.index(current)+1]:raise ValueError('must advance one phase')
        if current!='brief' and current not in workflow['records']:raise ValueError('phase record required')
        action=transition_action(state,target)
        apply_gate(state,dict(type='execute',gate_id=command['gate_id'],action=action),actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
        workflow['history'].append(dict(from_phase=current,to_phase=target,gate_id=command['gate_id'],operation_id=operation_id))
        workflow['phase']=target
    elif kind=='finish':
        _keys(command,{'type','outcome','reason'})
        if workflow['status']!='active':raise ValueError('workflow is terminal')
        if command['outcome'] not in {'stopped','escalated'}:raise ValueError('must stop or escalate')
        _text(command['reason'],'reason')
        if command['outcome']=='stopped' and ('synthesis' not in workflow['records'] or workflow['phase']!='synthesis'):raise ValueError('stop requires completed synthesis; escalate otherwise')
        if command['outcome']=='stopped' and workflow['record_bindings']['synthesis']!=research_content_digest(state):raise ValueError('synthesis is stale; escalate for fresh review')
        workflow.update(status=command['outcome'],stopping_reason=command['reason'])
    elif kind=='report':
        _keys(command,{'type','report_id'})
        _text(command['report_id'],'report_id')
        if workflow['status']=='active':raise ValueError('stop or escalate before reporting')
        if command['report_id'] in state.outputs:raise ValueError('duplicate report ID')
        from .reporting import build_report
        state.outputs[command['report_id']]=build_report(state,report_id=command['report_id'],actor=actor,timestamp=timestamp)
    else:raise ValueError('unsupported workflow command')
    state._change('workflow_'+kind,[workflow['workflow_id']],dict(actor=actor,rationale=rationale,operation_id=operation_id))
    for change in state.change_log[start:]:change['timestamp']=timestamp
    return [command['report_id']] if kind=='report' else [workflow['workflow_id']]
