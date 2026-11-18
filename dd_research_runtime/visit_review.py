"""Read-only inspection of a research visit and its original journal-bound context.

Local integrity checks do not establish source truth, identity or human acceptance.
Pre-journal records remain inspectable without inventing their original context.
"""
import copy
import json
from contextlib import closing
from .checkpoints import _ReadOnlySource
from .persistent_ingestion import PersistentEvidenceStore
from .review_ledger import ReviewLedger
from .state_journal import present,_state
from .double_diamond import PHASES,stage_currency,record_binding


def _context(state,phase,record):
    claims=set(record.get('claim_ids',[]));evidence=set(record.get('evidence_ids',[]));uncertainties=set(record.get('uncertainty_ids',[]))
    for item in record.get('alternatives',[]):
        claims.update(item['claim_ids']);evidence.update(item['evidence_ids'])
    for item in record.get('evaluations',[]):evidence.update(item['evidence_ids'])
    for cid in claims:
        evidence.update(state.claims[cid].get('evidence_ids',[]))
        uncertainties.update(state.claims[cid].get('material_uncertainties',[]))
    # Deliver criteria and alternatives are those in the same committed snapshot.
    definitions=state.workflow['records']
    return dict(brief=state.brief,scope=state.scope,questions=state.research_questions,claims={key:state.claims[key] for key in sorted(claims)},
        evidence={key:state.evidence[key] for key in sorted(evidence)},
        sources={state.evidence[key]['source_id']:state.sources.get(state.evidence[key]['source_id']) for key in sorted(evidence)},
        uncertainties={key:state.uncertainties[key] for key in sorted(uncertainties)},
        defined_problem=definitions.get('define') if phase=='deliver' else None,
        developed_alternatives=definitions.get('develop') if phase=='deliver' else None)


def read_visit(database,visit_id,*,expected_revision=None,_after_pin=None):
    """Return detached original context from one verified, pinned read transaction.

    The optional expected revision keeps a browser's case and review panels aligned.
    No constructor, migration, repair or write is performed. Unknown or pre-journal
    recording operations never fall back to current claims or source metadata.
    """
    if not isinstance(visit_id,str) or not visit_id or len(visit_id)>80:raise ValueError('invalid visit identifier')
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision<0):raise ValueError('invalid expected revision')
    source=_ReadOnlySource(database)
    store=object.__new__(PersistentEvidenceStore);store.ledger=object.__new__(ReviewLedger);store.ledger.path=str(source.path)
    with closing(source._connect()) as db:
        db.execute('BEGIN')
        state,sr,lr,_=store._verify_integrity(db)
        if expected_revision is not None and sr!=expected_revision:raise RuntimeError('This case changed. Refresh saved research before inspecting this visit.')
        if _after_pin is not None:_after_pin()
        workflow=getattr(state,'workflow',{})
        if workflow.get('workflow_version') not in {2,3}:raise ValueError('visit inspection requires a Double Diamond case')
        visits=workflow['visits'];matches=[(i,v) for i,v in enumerate(visits) if v['visit_id']==visit_id]
        if len(matches)!=1:raise ValueError('unknown research visit')
        index,visit=matches[0];phase=visit['phase']
        previous=next((v for v in reversed(visits[:index]) if v['phase']==phase and v['record'] is not None),None)
        record=visit['record'];latest_recorded=next((v['visit_id'] for v in reversed(visits) if v['phase']==phase and v['record'] is not None),None);projected=(visit_id==latest_recorded and record is not None and workflow['records'].get(phase)==record and workflow['record_bindings'].get(phase)==visit['binding'])
        result=dict(visit=visit,state_revision=sr,ledger_revision=lr,workflow_status=workflow['status'],active_phase=workflow['phase'],
            is_latest_visit=index==len(visits)-1,is_current_record=bool(projected),active_visit_id=visits[-1]['visit_id'],active_visit_recorded=visits[-1]['record'] is not None,
            current_binding_matches=bool(projected and stage_currency(state).get(phase,False)),
            context_status='not_recorded' if record is None else 'unavailable',context=None,recorded_at=None,recorded_revision=None,
            recording_actor=None,recording_reason=None,previous_visit_id=previous['visit_id'] if previous else None,
            previous_record=previous['record'] if previous else None,
            changed_fields=sorted(key for key in set(record or {})|set(previous['record'] if previous else {}) if (record or {}).get(key)!=(previous['record'] if previous else {}).get(key)) if previous and record is not None else [])
        if record is not None and present(db):
            row=db.execute("SELECT revision,request,after_snapshot,timestamp FROM state_mutations WHERE operation_id=? AND kind='workflow'",(visit.get('record_operation_id'),)).fetchone()
            if row:
                revision,encoded,snapshot,timestamp=row;request=json.loads(encoded);frozen=_state(snapshot);command=request['command']
                if command.get('type')!='record' or command.get('phase')!=phase or command.get('record')!=record or frozen.workflow['visits'][-1]!=visit:
                    raise ValueError('visit recording operation binding mismatch')
                if phase not in PHASES or record_binding(frozen,phase,record)!=visit['binding']:raise ValueError('visit original context binding mismatch')
                result.update(context_status='verified_original',context=_context(frozen,phase,record),recorded_at=timestamp,
                    recorded_revision=revision,recording_actor=request['actor'],recording_reason=request['rationale'])
        return copy.deepcopy(result)
