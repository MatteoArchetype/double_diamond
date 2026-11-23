"""Typed state mutation journal with a locally checksummed adoption checkpoint.

Legacy evidence histories remain as recorded. Post-adoption states are replayed
from the checkpoint. This is not signed history or external identity proof.
"""
import datetime as dt
import json
from .persistent_ingestion import _encode,_checksum
from .runtime import ResearchState, ResearchInvariantError

TABLES={'state_journal_policy','state_mutations'}


def present(db):
    names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    found=TABLES & names
    if found and found != TABLES:raise ValueError('state journal schema integrity mismatch')
    return bool(found)


def initialize_journal(db, validate_existing=None):
    with db:
        db.execute('BEGIN IMMEDIATE')
        existed=present(db)
        if not existed and validate_existing is not None and db.execute('SELECT 1 FROM research_state WHERE id=1').fetchone():
            validate_existing(db)
        db.execute('CREATE TABLE IF NOT EXISTS state_journal_policy (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, digest TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS state_mutations (revision INTEGER PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, request TEXT NOT NULL, request_digest TEXT NOT NULL, result TEXT NOT NULL, result_digest TEXT NOT NULL, before_hash TEXT NOT NULL, after_snapshot TEXT NOT NULL, after_hash TEXT NOT NULL, timestamp TEXT NOT NULL, previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL)')
        row=db.execute('SELECT 1 FROM state_journal_policy WHERE id=1').fetchone()
        if not row:
            if existed:raise ValueError('missing state journal policy integrity mismatch')
            current=db.execute('SELECT revision,snapshot,digest FROM research_state WHERE id=1').fetchone()
            policy=dict(version=1,adoption_revision=current[0] if current else 0,baseline_snapshot=current[1] if current else None,baseline_digest=current[2] if current else None)
            encoded=_encode(policy)
            db.execute('INSERT INTO state_journal_policy VALUES (1,?,?)',(encoded,_checksum(encoded)))


def bootstrap(db,snapshot):
    policy,digest=read_policy(db)
    if policy['baseline_snapshot'] is not None:raise ValueError('journal already bootstrapped')
    policy.update(baseline_snapshot=snapshot,baseline_digest=_checksum(snapshot))
    encoded=_encode(policy)
    db.execute('UPDATE state_journal_policy SET payload=?,digest=? WHERE id=1',(encoded,_checksum(encoded)))


def read_policy(db):
    row=db.execute('SELECT payload,digest FROM state_journal_policy WHERE id=1').fetchone()
    try:
        if not row or _checksum(row[0]) != row[1]:raise ValueError('policy checksum')
        policy=json.loads(row[0])
        if policy['version'] != 1 or type(policy['adoption_revision']) is not int or policy['adoption_revision'] < 0:raise ValueError('policy format')
        return policy,row[1]
    except (KeyError,TypeError,ValueError) as exc:raise ValueError('state journal policy integrity mismatch: '+str(exc)) from exc


def now():return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_changes(state,start,timestamp):
    for item in state.change_log[start:]:item['timestamp']=timestamp


def append(db,*,revision,operation_id,kind,request,result,before_snapshot,state,timestamp):
    _,root=read_policy(db)
    last=db.execute('SELECT entry_hash FROM state_mutations ORDER BY revision DESC LIMIT 1').fetchone()
    previous=last[0] if last else root
    request_encoded=_encode(request);result_encoded=_encode(result);after=_encode(state.snapshot())
    event=dict(revision=revision,operation_id=operation_id,kind=kind,request_digest=_checksum(request_encoded),result_digest=_checksum(result_encoded),before_hash=_checksum(before_snapshot),after_hash=_checksum(after),timestamp=timestamp,previous_hash=previous)
    entry=_checksum(_encode(event))
    db.execute('INSERT INTO state_mutations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (revision,operation_id,kind,request_encoded,event['request_digest'],result_encoded,event['result_digest'],event['before_hash'],after,event['after_hash'],timestamp,previous,entry))


def _state(snapshot):
    state=ResearchState();state.__dict__=json.loads(snapshot)
    ok,errors=state.validate()
    if not ok:raise ValueError('invalid journal state: '+str(errors))
    return state


def _replay_ingestion(db,state,oid,request,result,timestamp):
    row=db.execute('SELECT request_digest,review_digest,result FROM ingestion_operations WHERE operation_id=?',(oid,)).fetchone()
    if not row or request != dict(ingestion_request_digest=row[0],review_digest=row[1]) or result != json.loads(row[2]):
        raise ValueError('journal ingestion binding mismatch')
    archive=db.execute('SELECT payload FROM ingestion_review_archive WHERE operation_id=?',(oid,)).fetchone()
    if not archive:raise ValueError('journal ingestion requires retained review')
    documents=json.loads(archive[0])['documents'];start=len(state.change_log)
    for document,evidence in zip(documents,result['evidence']):
        if not document['synthetic']:
            metadata=document['metadata']
            state.add_source(dict(source_id=document['source_id'],title=metadata['title'],publisher=metadata['publisher'],url=metadata['url'],retrieved_at=metadata['retrieved_at'],published_at=metadata['published_at'],provenance=document['provenance'],independence_cluster=document['independence_cluster']))
        state.add_evidence(evidence)
        state._change('pipeline_retrieve_to_evidence',[evidence['evidence_id']])
    state._change('evidence_review',[item['evidence_id'] for item in result['evidence']],row[1])
    normalize_changes(state,start,timestamp)


def verify(db,state,revision,ingestion_operations):
    if not present(db):
        if len(ingestion_operations) != revision:raise ValueError('operation history revision integrity mismatch')
        return dict(adoption_revision=revision,ingestion_mutations=0,analysis_mutations=0,journal_entries=0)
    policy,previous=read_policy(db);baseline=policy['adoption_revision'];snapshot=policy['baseline_snapshot']
    try:
        if snapshot is None or _checksum(snapshot) != policy['baseline_digest'] or baseline > revision:raise ValueError('invalid adoption checkpoint')
        legacy=[json.loads(row[3])['state_revision'] for row in ingestion_operations if json.loads(row[3])['state_revision'] <= baseline]
        if len(legacy) != baseline or any(value != index for index,value in enumerate(sorted(legacy),1)):raise ValueError('legacy ingestion coverage mismatch')
        current=_state(snapshot);prior_hash=_checksum(snapshot)
        rows=db.execute('SELECT revision,operation_id,kind,request,request_digest,result,result_digest,before_hash,after_snapshot,after_hash,timestamp,previous_hash,entry_hash FROM state_mutations ORDER BY revision').fetchall()
        if len(rows) != revision-baseline:raise ValueError('missing state mutation revision integrity mismatch')
        seen_ingestions=set();analysis_count=0;gate_events={};gate_count=0;workflow_count=0;acceptance_count=0
        for index,row in enumerate(rows,baseline+1):
            sr,oid,kind,req,reqhash,res,reshash,before,after,afterhash,timestamp,prev,entry=row
            event=dict(revision=sr,operation_id=oid,kind=kind,request_digest=reqhash,result_digest=reshash,before_hash=before,after_hash=afterhash,timestamp=timestamp,previous_hash=prev)
            if (sr != index or prev != previous or before != prior_hash or _checksum(req)!=reqhash or _checksum(res)!=reshash or _checksum(after)!=afterhash or _checksum(_encode(event))!=entry):
                raise ValueError('mutation chain mismatch')
            parsed=dt.datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:raise ValueError('mutation timestamp must be timezone-aware')
            request,result=json.loads(req),json.loads(res)
            if result.get('operation_id') != oid or result.get('state_revision') != sr:raise ValueError('mutation result identity mismatch')
            if kind == 'ingestion':
                _replay_ingestion(db,current,oid,request,result,timestamp);seen_ingestions.add(oid)
            elif kind in {'analysis','gate','workflow','acceptance'}:
                from .analysis_transactions import apply_commands
                if db.execute('SELECT 1 FROM ingestion_operations WHERE operation_id=?',(oid,)).fetchone():raise ValueError('operation ID collision')
                field='commands' if kind=='analysis' else 'command'
                if set(request) != {'actor','rationale',field}:raise ValueError('invalid mutation request')
                from .gate_transactions import apply_gate
                commands=request[field] if kind=='analysis' else [request[field]]
                for command in commands:
                    if 'gate_id' in command and (kind in {'analysis','workflow'} or command.get('type')=='execute'):
                        gate=current.human_gates.get(command['gate_id'],{})
                        proposal=gate_events.get(gate.get('proposal_operation_id'),{})
                        decision=gate_events.get(gate.get('decision_operation_id'),{})
                        if proposal.get('type')!='propose' or decision.get('decision')!='approve' or proposal.get('gate_id')!=command['gate_id'] or decision.get('gate_id')!=command['gate_id']:
                            raise ValueError('gate authorization lacks durable proposal/decision history')
                from .workflow import apply_workflow
                handler={'analysis':apply_commands,'gate':apply_gate,'workflow':apply_workflow}.get(kind)
                from .acceptance import apply_acceptance
                if kind=='acceptance':handler=apply_acceptance
                changed=handler(current,request[field],actor=request['actor'],rationale=request['rationale'],operation_id=oid,timestamp=timestamp,**({'db':db} if kind=='acceptance' else {}))
                if result != dict(operation_id=oid,state_revision=sr,kind=kind,actor=request['actor'],changed_ids=changed):raise ValueError('mutation result mismatch')
                analysis_count+=kind=='analysis'
                workflow_count+=kind=='workflow'
                acceptance_count+=kind=='acceptance'
                if kind=='gate':gate_events[oid]=request[field];gate_count+=1
            else:raise ValueError('unknown mutation kind')
            if _encode(current.snapshot()) != after:raise ValueError('replayed state mismatch')
            previous=entry;prior_hash=afterhash
        expected={r[0] for r in ingestion_operations if json.loads(r[3])['state_revision']>baseline}
        if seen_ingestions != expected or _encode(current.snapshot()) != _encode(state.snapshot()):raise ValueError('mutation/state coverage mismatch')
        coverage=dict(adoption_revision=baseline,ingestion_mutations=len(seen_ingestions),analysis_mutations=analysis_count,journal_entries=len(rows))
        if gate_count:coverage['gate_mutations']=gate_count
        if workflow_count:coverage['workflow_mutations']=workflow_count
        if acceptance_count:coverage['acceptance_mutations']=acceptance_count
        return coverage
    except (KeyError,TypeError,ValueError,AttributeError,PermissionError,ResearchInvariantError) as exc:
        raise ValueError('state mutation journal integrity mismatch: '+str(exc)) from exc
