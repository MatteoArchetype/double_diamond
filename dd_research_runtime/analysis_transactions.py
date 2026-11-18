"""Typed advisory analysis operations; no source, gate or publication mutation."""
import copy
from assessment import assess, DIMENSIONS
from claim_disposition import make_disposition, requires_human_review
from .persistent_ingestion import _encode, _checksum


def _text(value,name):
    if not isinstance(value,str) or not value.strip():raise ValueError(name+' must be a nonblank string')
    return value


def _keys(value,required,optional=()):
    if not isinstance(value,dict) or not set(required)<=set(value) or set(value)-set(required)-set(optional):
        raise ValueError('invalid analysis command fields')


def _ids(value,name):
    if not isinstance(value,list) or any(not isinstance(x,str) or not x.strip() for x in value) or len(set(value)) != len(value):
        raise ValueError(name+' must be unique string IDs')
    return value


def _origin(state,ids):
    if not ids:return 'none'
    flags=[state.evidence[eid].get('synthetic') is True for eid in ids]
    return 'synthetic_only' if all(flags) else 'mixed' if any(flags) else 'non_synthetic'


CLAIM_FIELDS={'claim','claim_type','disposition','evidence_ids','confidence','status','material_uncertainties'}


def _validate_claim(state,claim):
    _text(claim.get('claim_id'),'claim_id');_text(claim.get('claim'),'claim')
    if claim.get('claim_type','descriptive') not in {'descriptive','causal','generalisation'}:raise ValueError('unsupported claim_type')
    ids=_ids(claim.get('evidence_ids',[]),'evidence_ids')
    if any(e not in state.evidence for e in ids):raise ValueError('claim references missing evidence')
    disposition=claim.get('disposition','draft');_text(disposition,'disposition')
    if claim.get('claim_type','descriptive') in {'causal','generalisation'} and not ids and disposition not in {'hypothesis','unknown','unresolved'}:
        raise ValueError('causal/generalisation claim requires evidence or unresolved status')
    for name in ('confidence','status'):
        if name in claim:_text(claim[name],name)
    if 'material_uncertainties' in claim:_ids(claim['material_uncertainties'],'material_uncertainties')
    if any(uid not in state.uncertainties for uid in claim.get('material_uncertainties',[])):raise ValueError('claim references missing uncertainty')
    claim['evidence_origin']=_origin(state,ids)
    claim['analysis_status']='advisory'


def _validate_contradiction(state,record):
    _text(record.get('contradiction_id'),'contradiction_id');_text(record.get('issue'),'issue')
    for name in ('claim_a','claim_b'):
        if record.get(name) not in state.claims:raise ValueError('contradiction references missing claim')
    if record['claim_a'] == record['claim_b']:raise ValueError('contradiction requires distinct claims')
    if record.get('disposition','unresolved') not in {'open','unresolved','resolved','narrowed','qualified','withdrawn'}:
        raise ValueError('invalid contradiction disposition')
    if record.get('disposition') in {'resolved','narrowed','qualified','withdrawn'}:_text(record.get('resolution_basis'),'resolution_basis')


def apply_commands(state,commands,*,actor,rationale,operation_id,timestamp):
    """Deterministic staged application used by both writes and journal replay."""
    _text(actor,'actor');_text(rationale,'rationale');_text(operation_id,'operation_id')
    if not isinstance(commands,list) or not 1 <= len(commands) <= 100:raise ValueError('analysis requires 1 to 100 commands')
    start=len(state.change_log);changed=[]
    for command in commands:
        if not isinstance(command,dict):raise ValueError('analysis command must be a mapping')
        kind=command.get('type')
        if kind == 'add_claim':
            _keys(command,{'type','record'})
            record=copy.deepcopy(command['record'])
            _keys(record,{'claim_id','claim'},CLAIM_FIELDS)
            if record.get('disposition','draft') not in {'draft','unknown','unresolved','hypothesis'}:
                raise PermissionError('claim requires a durable human disposition decision')
            if record.get('status','draft') not in {'draft','unresolved','unknown','hypothesis'}:raise ValueError('new claims must start in an advisory draft/unresolved status')
            _validate_claim(state,record);state.add_claim(record);changed.append(record['claim_id'])
        elif kind == 'update_claim':
            _keys(command,{'type','claim_id','patch'})
            cid=_text(command['claim_id'],'claim_id')
            if cid not in state.claims:raise ValueError('unknown claim')
            patch=copy.deepcopy(command['patch'])
            if not isinstance(patch,dict) or not patch or set(patch)-(CLAIM_FIELDS-{'status','disposition'}):raise ValueError('invalid claim patch')
            candidate=copy.deepcopy(state.claims[cid]);candidate.update(patch);_validate_claim(state,candidate)
            patch['evidence_origin']=candidate['evidence_origin'];patch['analysis_status']='advisory'
            state.update_claim(cid,patch,rationale,operation_id);changed.append(cid)
        elif kind == 'assess_evidence':
            _keys(command,{'type','assessment_id','evidence_id','claim_id','dimensions','limitations','rationale'})
            aid=_text(command['assessment_id'],'assessment_id')
            eid,cid=command['evidence_id'],command['claim_id']
            if eid not in state.evidence or cid not in state.claims or eid not in state.claims[cid].get('evidence_ids',[]):
                raise ValueError('assessment must reference evidence attached to a known claim')
            dimensions=command['dimensions']
            if not isinstance(dimensions,dict) or set(dimensions)!=set(DIMENSIONS) or any(v not in {'low','medium','high','unknown','not_applicable'} for v in dimensions.values()):
                raise ValueError('assessment requires all supported qualitative dimensions')
            limitations=command['limitations']
            if not isinstance(limitations,list) or any(not isinstance(x,str) or not x.strip() for x in limitations):raise ValueError('invalid assessment limitations')
            _text(command['rationale'],'assessment rationale')
            collection=state.__dict__.setdefault('assessments',{})
            if aid in collection:raise ValueError('duplicate assessment ID')
            result=assess(eid,cid,dimensions,limitations,command['rationale']).to_dict()
            result.update(assessment_id=aid,assessor=actor,status='advisory',evidence_origin=_origin(state,[eid]),claim_digest=_checksum(_encode(state.claims[cid])),evidence_digest=_checksum(_encode(state.evidence[eid])))
            collection[aid]=result;state._change('assess_evidence',[aid,eid,cid],rationale);changed.append(aid)
        elif kind == 'add_contradiction':
            _keys(command,{'type','record'})
            record=copy.deepcopy(command['record'])
            _keys(record,{'contradiction_id','claim_a','claim_b','issue'},{'disposition','resolution_basis'})
            _validate_contradiction(state,record);state.add_contradiction(record);changed.append(record['contradiction_id'])
        elif kind == 'update_contradiction':
            _keys(command,{'type','contradiction_id','patch'})
            xid=_text(command['contradiction_id'],'contradiction_id')
            if xid not in state.contradictions:raise ValueError('unknown contradiction')
            patch=command['patch']
            if not isinstance(patch,dict) or not patch or set(patch)-{'issue','disposition','resolution_basis'}:raise ValueError('invalid contradiction patch')
            record=copy.deepcopy(state.contradictions[xid]);record.update(copy.deepcopy(patch));_validate_contradiction(state,record)
            state.contradictions[xid]=record;state._change('update_contradiction',[xid],rationale);changed.append(xid)
        elif kind == 'put_uncertainty':
            _keys(command,{'type','record'})
            record=copy.deepcopy(command['record'])
            _keys(record,{'uncertainty_id','question','status'},{'resolution_basis'})
            uid=_text(record['uncertainty_id'],'uncertainty_id');_text(record['question'],'question')
            if record['status'] not in {'open','unresolved','resolved','closed'}:raise ValueError('invalid uncertainty status')
            if record['status'] in {'resolved','closed'}:_text(record.get('resolution_basis'),'resolution_basis')
            state.uncertainties[uid]=record;state._change('put_uncertainty',[uid],rationale);changed.append(uid)
        elif kind == 'set_disposition':
            _keys(command,{'type','disposition_id','claim_id','disposition','rationale','evidence_ids','prior_status','new_status','material_uncertainties','decision_relevance'}, {'review_required','foundational','consequential','gate_id'})
            did=_text(command['disposition_id'],'disposition_id');cid=command['claim_id']
            if cid not in state.claims:raise ValueError('unknown claim')
            claim=state.claims[cid]
            if command['prior_status'] != claim.get('status','draft'):raise ValueError('stale prior claim status')
            ids=_ids(command['evidence_ids'],'evidence_ids')
            if any(e not in state.evidence for e in ids):raise ValueError('disposition references missing evidence')
            _ids(command['material_uncertainties'],'material_uncertainties')
            for name in ('prior_status','new_status','decision_relevance','rationale'):_text(command[name],name)
            for name in ('review_required','foundational','consequential'):
                if name in command and type(command[name]) is not bool:raise ValueError(name+' must be boolean')
            disposition=make_disposition(cid,command['disposition'],command['rationale'],ids,command['prior_status'],command['new_status'],command['material_uncertainties'],command['decision_relevance'],command.get('review_required',False))
            if requires_human_review(disposition,command.get('foundational',False),command.get('consequential',False)):
                from .gate_transactions import consume
                consume(state,command,operation_id)
            elif 'gate_id' in command:
                from .gate_transactions import consume
                consume(state,command,operation_id)
            allowed_status={'retain_bounded':{'retained'},'narrow':{'narrowed'},'qualify':{'qualified'},'unresolved':{'unresolved','unknown'},'withdraw':{'withdrawn','retracted'},'promote_to_hypothesis':{'hypothesis'}}
            if command['new_status'] not in allowed_status.get(command['disposition'],set()):raise ValueError('new_status does not match advisory disposition')
            collection=state.__dict__.setdefault('claim_dispositions',{})
            if did in collection:raise ValueError('duplicate disposition ID')
            patch=dict(disposition=command['disposition'],status=command['new_status'],evidence_ids=ids,material_uncertainties=command['material_uncertainties'])
            candidate=copy.deepcopy(claim);candidate.update(patch);_validate_claim(state,candidate);patch['evidence_origin']=candidate['evidence_origin'];patch['analysis_status']='advisory'
            state.update_claim(cid,patch,command['rationale'],operation_id)
            record=disposition.to_dict();record.update(disposition_id=did,actor=actor,status='advisory',evidence_origin=candidate['evidence_origin'])
            if 'gate_id' in command:record['decision_gate_id']=command['gate_id']
            collection[did]=record;state._change('set_disposition',[did,cid],rationale);changed.append(did)
        else:raise ValueError('unsupported analysis command')
    state._change('analysis_transaction',changed,dict(actor=actor,rationale=rationale,operation_id=operation_id))
    for change in state.change_log[start:]:change['timestamp']=timestamp
    ok,errors=state.validate()
    if not ok:raise ValueError('invalid staged analysis state: '+str(errors))
    return changed


def assessment_is_current(state, assessment_id):
    """An advisory assessment applies to the exact claim/evidence versions recorded."""
    record=state.__dict__.get('assessments',{}).get(assessment_id)
    if record is None:raise KeyError('unknown assessment')
    claim=state.claims.get(record['claim_id']);evidence=state.evidence.get(record['evidence_id'])
    return (claim is not None and evidence is not None
            and record.get('claim_digest') == _checksum(_encode(claim))
            and record.get('evidence_digest') == _checksum(_encode(evidence)))
