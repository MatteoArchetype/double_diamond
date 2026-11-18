"""Deterministic, host-authorized gate proposals and decisions.

Callbacks authenticate callers at the write boundary; journal replay verifies
recorded decisions without pretending that local hashes establish identity.
"""
import copy
from .persistent_ingestion import _encode, _checksum


def binding(command):
    return _checksum(_encode({k:v for k,v in command.items() if k != 'gate_id'}))


def target_digest(state, command):
    if command.get('type') == 'gated_action':return binding(command)
    cid=command.get('claim_id')
    if cid not in state.claims:raise ValueError('unknown target claim')
    return _checksum(_encode(state.claims[cid]))


def apply_gate(state, command, *, actor, rationale, operation_id, timestamp):
    from .analysis_transactions import _keys, _text, apply_commands
    kind=command.get('type');gid=_text(command.get('gate_id'),'gate_id')
    start=len(state.change_log)
    if kind == 'propose':
        _keys(command,{'type','gate_id','action'})
        action=copy.deepcopy(command['action'])
        if not isinstance(action,dict) or action.get('type') not in {'set_disposition','gated_action'} or 'gate_id' in action:
            raise ValueError('gate requires an exact disposition action without gate_id')
        if gid in state.human_gates:raise ValueError('duplicate gate ID')
        if action['type']=='gated_action':
            from .runtime import GATED_ACTIONS
            _keys(action,{'type','action','payload'})
            if action['action'] not in GATED_ACTIONS or not isinstance(action['payload'],dict):raise ValueError('invalid bounded gate action')
        digest=target_digest(state,action)
        proposal=dict(gate_id=gid,gate_type=action.get('action','claim_disposition'),status='pending_review',action=action,
                      action_digest=binding(action),target_digest=digest,proposer=actor,proposal_rationale=rationale,
                      proposal_operation_id=operation_id)
        # Validate the complete proposed action against a private staged state.
        if action['type']=='set_disposition':
            trial=copy.deepcopy(state);trial.human_gates[gid]=dict(proposal,status='approved',decision_actor=actor,decision_operation_id=operation_id)
            apply_commands(trial,[dict(action,gate_id=gid)],actor=actor,rationale=rationale,operation_id=operation_id,timestamp=timestamp)
        state.human_gates[gid]=proposal
    elif kind == 'decide':
        _keys(command,{'type','gate_id','decision','proposal_digest'})
        gate=state.human_gates.get(gid)
        if not gate or 'action_digest' not in gate or 'proposal_operation_id' not in gate:
            raise PermissionError('durable gate proposal required')
        if gate['status'] != 'pending_review':raise PermissionError('gate is not pending')
        if command['proposal_digest'] != binding(gate['action']):raise PermissionError('proposal digest mismatch')
        if target_digest(state,gate['action']) != gate['target_digest']:raise PermissionError('stale gate target')
        if command['decision'] not in {'approve','reject'}:raise ValueError('decision must approve or reject')
        gate.update(status='approved' if command['decision']=='approve' else 'rejected',decision_actor=actor,
                    decision_rationale=rationale,decision_operation_id=operation_id)
    elif kind == 'execute':
        _keys(command,{'type','gate_id','action'})
        action=command['action'];gate=state.human_gates.get(gid)
        if not isinstance(action,dict) or action.get('type') != 'gated_action':raise ValueError('bounded gated_action required')
        if not gate or gate.get('status') != 'approved' or not gate.get('decision_operation_id') or gate.get('action_digest') != binding(action) or gate.get('gate_type') != action.get('action'):
            raise PermissionError('approved exact gate action required')
        gate.update(status='executed',execution_operation_id=operation_id)
    else:raise ValueError('unsupported gate command')
    state._change('gate_'+kind,[gid],dict(actor=actor,rationale=rationale,operation_id=operation_id))
    for change in state.change_log[start:]:change['timestamp']=timestamp
    return [gid]


def consume(state, command, operation_id):
    gid=command.get('gate_id');gate=state.human_gates.get(gid)
    if (not gate or gate.get('status') != 'approved' or gate.get('gate_type') != 'claim_disposition'
        or not gate.get('decision_operation_id') or not gate.get('proposal_operation_id')):
        raise PermissionError('disposition requires a durable human decision')
    if gate.get('action_digest') != binding(command) or gate.get('target_digest') != target_digest(state,command):
        raise PermissionError('gate action or target mismatch')
    gate.update(status='executed',execution_operation_id=operation_id)
    state._change('consume_gate',[gid],operation_id)
    return gid
