"""Immutable proposed research agendas anchored to current criterion-linked reports.

Planning is not permission to contact participants, fetch sources or run experiments.
"""
import copy
from .analysis_transactions import _keys,_text,_ids
from .persistent_ingestion import _encode,_checksum
from .reporting import report_is_current

PRIORITIES={'high':0,'medium':1,'low':2}
METHODS={'desk_review','interview','survey','experiment','analysis'}


def _ordered(items):
    remaining={item['item_id']:item for item in items};finished=[]
    while remaining:
        available=[item for item in remaining.values() if set(item['depends_on'])<=set(finished)]
        if not available:raise ValueError('research dependencies contain a cycle')
        chosen=min(available,key=lambda item:(PRIORITIES[item['priority']],item['item_id']))
        finished.append(chosen['item_id']);del remaining[chosen['item_id']]
    return finished


def apply_agenda(state,command,*,actor,rationale,operation_id,timestamp):
    _keys(command,{'type','agenda_id','report_id','report_digest','items'})
    aid=_text(command['agenda_id'],'agenda_id')
    if aid in getattr(state,'research_agendas',{}):raise ValueError('agenda ID already exists')
    report=state.outputs.get(command['report_id'])
    if not report or not report.get('decision_trace'):raise ValueError('criterion-linked research report required')
    if not report_is_current(state,command['report_id']):raise ValueError('current research report required')
    if command['report_digest']!=report['content_digest']:raise ValueError('agenda report digest mismatch')
    if _checksum(_encode({k:v for k,v in report.items() if k!='content_digest'}))!=report['content_digest']:raise ValueError('report content digest mismatch')
    gaps={row['criterion_index']:row for row in report['decision_trace']['criteria'] if row['outcome']!='met'}
    if not gaps:raise ValueError('no unmet criteria to plan research for')
    items=command['items']
    if not isinstance(items,list) or not 1<=len(items)<=20:raise ValueError('agenda requires 1 to 20 research items')
    seen=set();covered=set();planned=[]
    for item in items:
        _keys(item,{'item_id','criterion_index','evidence_gap','question','method','target_phase','priority','priority_rationale','success_signal','effort','depends_on'})
        iid=_text(item['item_id'],'item_id');index=item['criterion_index']
        if iid in seen:raise ValueError('duplicate research item ID')
        seen.add(iid)
        if type(index) is not int or index not in gaps:raise ValueError('agenda items must refer to current unmet criteria')
        covered.add(index)
        for name in ('evidence_gap','question','priority_rationale','success_signal'):_text(item[name],name)
        if item['method'] not in METHODS:raise ValueError('unknown research method')
        if item['target_phase'] not in {'discover','define','develop'}:raise ValueError('next research must target Discover, Define or Develop')
        if item['priority'] not in PRIORITIES or item['effort'] not in {'small','medium','large'}:raise ValueError('invalid research priority or effort')
        _ids(item['depends_on'],'depends_on')
        if iid in item['depends_on']:raise ValueError('research cannot depend on itself')
        saved=copy.deepcopy(item);gap=gaps[index]
        saved.update(criterion=gap['criterion'],criterion_outcome=gap['outcome'],recorded_next_research=gap['next_research'],
                     evidence_ids=gap['evidence_ids'],evidence_origin=gap['evidence_origin'],status='proposed',execution_authorized=False,
                     required_gate_types=['primary_research'] if item['method'] in {'interview','survey','experiment'} else [])
        planned.append(saved)
    if covered!=set(gaps):raise ValueError('every unmet criterion requires a research item')
    if any(dep not in seen for item in planned for dep in item['depends_on']):raise ValueError('unknown research dependency')
    order=_ordered(planned)
    from .workflow import domain_digest
    agenda=dict(agenda_id=aid,report_id=command['report_id'],report_digest=command['report_digest'],context_digest=domain_digest(state),
                actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp,items=planned,proposed_order=order,
                status='proposed',execution_authorized=False,
                limitations=['Priorities and methods are recorded planning judgments, not validated study designs.',
                             'Gate hints do not grant authorization. Human review and exact action approval remain required.',
                             'No participant contact, external retrieval or experiment is performed by planning.'])
    state.__dict__.setdefault('research_agendas',{})[aid]=agenda
    start=len(state.change_log);state._change('plan_research',[aid,command['report_id']],dict(actor=actor,rationale=rationale,operation_id=operation_id))
    for item in state.change_log[start:]:item['timestamp']=timestamp
    return [aid]


def inspect_agenda(state,agenda_id):
    if agenda_id not in getattr(state,'research_agendas',{}):raise KeyError('unknown research agenda')
    agenda=copy.deepcopy(state.research_agendas[agenda_id])
    from .workflow import domain_digest
    current=agenda['context_digest']==domain_digest(state)
    agenda['basis_report_current']=report_is_current(state,agenda['report_id'])
    agenda.update(current=current,status='proposed' if current else 'stale',execution_authorized=False)
    return agenda


def render_markdown(agenda):
    import html
    import json
    import re
    def safe(value):
        text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
        return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])',r'\\\1',html.escape(text,quote=False).replace('\n',' '))
    def field(name,value):return '- **'+name+':** '+safe(value)
    lines=['# Proposed research agenda','','Planning only — no external action is authorized.',field('Status',agenda['status']),field('Based on report',agenda['report_id']),field('Report digest',agenda['report_digest']),field('Planner',agenda['actor'])]
    by_id={item['item_id']:item for item in agenda['items']}
    for iid in agenda['proposed_order']:
        item=by_id[iid];lines += ['','## '+safe(iid),field('Criterion',item['criterion']),field('Current outcome',item['criterion_outcome']),field('Evidence gap',item['evidence_gap']),
            field('Research question',item['question']),field('Method',item['method']),field('Return to phase',item['target_phase']),field('Priority',item['priority']),field('Why this priority',item['priority_rationale']),
            field('What would count as progress',item['success_signal']),field('Estimated effort',item['effort']),field('Depends on',item['depends_on']),field('Existing evidence IDs',item['evidence_ids']),
            field('Evidence origin',item['evidence_origin']),field('Required action gate types',item['required_gate_types'])]
    lines += ['','## Limitations']+['- '+safe(text) for text in agenda['limitations']]
    return '\n'.join(lines)+'\n'


def read_agenda(database,agenda_id):
    from contextlib import closing
    from .checkpoints import _ReadOnlySource
    from .persistent_ingestion import PersistentEvidenceStore
    from .review_ledger import ReviewLedger
    source=_ReadOnlySource(database);store=object.__new__(PersistentEvidenceStore);store.ledger=object.__new__(ReviewLedger)
    with closing(source._connect()) as db:
        db.execute('BEGIN');state,revision,_,_=store._verify_integrity(db)
        result=inspect_agenda(state,agenda_id);result['state_revision']=revision;return result


def export_agenda(database,agenda_id,destination,*,format='markdown',allow_stale=False):
    import json
    import tempfile
    from pathlib import Path
    from .checkpoints import _destination,_publish
    if format not in {'markdown','json'} or type(allow_stale) is not bool:raise ValueError('invalid agenda export options')
    destination=_destination(destination);agenda=read_agenda(database,agenda_id)
    if not agenda['current'] and not allow_stale:raise ValueError('research agenda is stale; create a new agenda or explicitly export its historical context')
    content=render_markdown(agenda) if format=='markdown' else json.dumps(agenda,indent=2,ensure_ascii=False)+'\n'
    with tempfile.TemporaryDirectory(prefix='.dd-agenda-',dir=destination.parent) as temp:
        staged=Path(temp)/'agenda';staged.write_text(content,encoding='utf-8');_publish(staged,destination,None)
    return dict(agenda_id=agenda_id,destination=str(destination),status=agenda['status'],execution_authorized=False)
