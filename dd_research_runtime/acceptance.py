"""Host acceptance of an exact, current real-source case; never self-certification."""
import copy
import datetime as dt
import json
from .analysis_transactions import _keys,_text,_ids
from .persistent_ingestion import _encode,_checksum
from .reporting import report_is_current
from .evidence_review import _digest


def _aware(value,name):
    _text(value,name)
    try:parsed=dt.datetime.fromisoformat(value)
    except ValueError as exc:raise ValueError(name+' must be an ISO timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:raise ValueError(name+' must have a timezone')
    return parsed


def inspect_case(state,report_id,*,db):
    """Readiness is structural evidence, not authentication or source independence."""
    report=state.outputs.get(report_id)
    if not isinstance(report,dict) or 'content_digest' not in report:raise KeyError('unknown saved report')
    blockers=[]
    if not report_is_current(state,report_id):blockers.append('report_stale')
    workflow=report.get('workflow',{})
    iterative=workflow.get('workflow_version') in {2,3}
    phases={'discover','define','develop','deliver'} if iterative else {'discovery','definition','alternatives','synthesis'}
    if workflow.get('status')!='stopped' or set(workflow.get('records',{}))!=phases or (not iterative and len(workflow.get('history',[]))!=4) or (iterative and len(workflow.get('history',[]))<3):
        blockers.append('complete_stopped_workflow_required')
    if set(report.get('stage_currency',{}))!=phases or not all(report.get('stage_currency',{}).values()):blockers.append('current_stage_records_required')
    if report.get('status')!='draft' or report.get('publication_authorized') is not False:blockers.append('unpublished_draft_required')
    if _checksum(_encode({k:v for k,v in report.items() if k!='content_digest'}))!=report['content_digest']:raise ValueError('report content digest mismatch')
    referenced={e['evidence_id'] for claim in report['claims'] for e in claim['evidence']}
    referenced.update(workflow.get('records',{}).get('discovery',{}).get('evidence_ids',[]))
    for alternative in workflow.get('records',{}).get('alternatives',{}).get('alternatives',[]):referenced.update(alternative['evidence_ids'])
    if iterative:
        referenced.update(workflow.get('records',{}).get('discover',{}).get('evidence_ids',[]))
        for alternative in workflow.get('records',{}).get('develop',{}).get('alternatives',[]):referenced.update(alternative['evidence_ids'])
        for evaluation in workflow.get('records',{}).get('deliver',{}).get('evaluations',[]):referenced.update(evaluation['evidence_ids'])
        for visit in workflow.get('visits',[]):
            record=visit.get('record') or {}
            referenced.update(record.get('evidence_ids',[]))
            for item in record.get('alternatives',[])+record.get('evaluations',[]):referenced.update(item['evidence_ids'])
    real_ids=sorted(eid for eid in referenced if state.evidence[eid].get('synthetic') is False)
    synthetic_ids=sorted(referenced-set(real_ids))
    if not real_ids:blockers.append('real_source_evidence_required')
    retained={}
    for oid,payload in db.execute('SELECT operation_id,payload FROM ingestion_review_archive'):
        request=json.loads(payload)
        for index,doc in enumerate(request['documents']):
            eid=doc['source_id']
            if eid not in real_ids:continue
            snapshot=request.get('source_snapshots',{}).get(eid)
            if snapshot is None:continue
            digest=_digest(dict(source_id=eid,text=snapshot['text'],location=snapshot['location']))
            if digest!=request['review']['snapshot_digests'][index]:raise ValueError('snapshot binding mismatch')
            retained[eid]=dict(evidence_id=eid,ingestion_operation_id=oid,snapshot_digest=digest,source_url=doc['metadata']['url'],
                               source_id=eid,location=snapshot['location'],reviewer=request['review']['reviewer'],review_digest=request['review']['record_digest'])
    missing=sorted(set(real_ids)-set(retained))
    if missing:blockers.append('retained_real_source_snapshots_required')
    return dict(report_id=report_id,report_digest=report['content_digest'],structurally_ready=not blockers,blockers=blockers,
                real_evidence_ids=real_ids,synthetic_evidence_ids=synthetic_ids,missing_snapshot_evidence_ids=missing,
                source_bindings=[retained[eid] for eid in sorted(retained)],human_review_required=True)


def apply_acceptance(state,command,*,actor,rationale,operation_id,timestamp,db):
    _text(actor,'actor');_text(rationale,'rationale')
    _keys(command,{'type','acceptance_id','report_id','report_digest','decision','review_mode','source_attestations','limitations'})
    if command['type']!='decide':raise ValueError('unsupported acceptance command')
    aid=_text(command['acceptance_id'],'acceptance_id')
    if command['decision'] not in {'accept','reject'}:raise ValueError('decision must accept or reject')
    if command['review_mode'] not in {'host','fixture'}:raise ValueError('review_mode must be host or fixture')
    _ids(command['limitations'],'limitations')
    if not command['limitations']:raise ValueError('explicit limitations required')
    records=state.__dict__.get('acceptance_records',{})
    if aid in records:raise ValueError('duplicate acceptance ID')
    inspection=inspect_case(state,command['report_id'],db=db)
    if command['report_digest']!=inspection['report_digest']:raise ValueError('report digest mismatch')
    if 'report_stale' in inspection['blockers']:raise ValueError('current report required for acceptance decision')
    attestations=command['source_attestations']
    if not isinstance(attestations,list):raise ValueError('source_attestations must be a list')
    if command['decision']=='accept':
        if not inspection['structurally_ready']:raise ValueError('case not ready: '+','.join(inspection['blockers']))
        expected={item['evidence_id']:item for item in inspection['source_bindings']};seen=set()
        for item in attestations:
            _keys(item,{'evidence_id','ingestion_operation_id','snapshot_digest','source_url','acquired_at','acquisition_method','independence_basis'})
            eid=item['evidence_id']
            if eid not in expected or eid in seen:raise ValueError('unexpected or duplicate source attestation')
            seen.add(eid)
            for key in ('ingestion_operation_id','snapshot_digest','source_url'):
                if item[key]!=expected[eid][key]:raise ValueError('source attestation binding mismatch')
            for key in ('acquisition_method','independence_basis'):_text(item[key],key)
            if _aware(item['acquired_at'],'acquired_at')>_aware(timestamp,'timestamp'):raise ValueError('source acquisition cannot be in the future')
        if seen!=set(expected):raise ValueError('all real-source snapshot attestations required')
    elif attestations:raise ValueError('rejection must not assert source verification')
    status=('host_accepted' if command['review_mode']=='host' else 'fixture_accepted') if command['decision']=='accept' else 'rejected'
    record=copy.deepcopy(command)
    record.update(status=status,actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp,
                  sequence=len(records)+1,scope='bounded_case',source_bindings=inspection['source_bindings'])
    state.__dict__.setdefault('acceptance_records',{})[aid]=record
    start=len(state.change_log);state._change('acceptance_decision',[aid,command['report_id']],dict(actor=actor,operation_id=operation_id))
    for change in state.change_log[start:]:change['timestamp']=timestamp
    return [aid]


def case_status(state,report_id,*,db):
    result=inspect_case(state,report_id,db=db)
    records=[r for r in getattr(state,'acceptance_records',{}).values() if r['report_id']==report_id]
    latest=max(records,key=lambda r:r['sequence']) if records else None
    status=latest['status'] if latest else 'pending_human_review'
    if latest and (latest['report_digest']!=result['report_digest'] or 'report_stale' in result['blockers']):status='stale'
    result.update(status=status,host_accepted=status=='host_accepted' and result['structurally_ready'],latest_decision=copy.deepcopy(latest),
                  software_release_certified=False,publication_authorized=False)
    return result
