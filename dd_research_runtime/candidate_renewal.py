"""Explicit stale-candidate renewal, with immutable lineage and fresh review context."""
import json
from contextlib import closing
from dataclasses import replace

from .persistent_ingestion import _encode, _checksum


def _link(db, child_id):
    row = db.execute('SELECT parent_id,payload,digest FROM candidate_renewals WHERE child_id=?',(child_id,)).fetchone()
    if row is None:
        return None
    parent_id, encoded, digest = row
    if _checksum(encoded) != digest:
        raise ValueError('renewal integrity mismatch')
    try:
        data = json.loads(encoded)
        parent = db.execute('SELECT payload,digest,status FROM pending_retrievals WHERE candidate_id=?',(parent_id,)).fetchone()
        child = db.execute('SELECT payload,digest FROM pending_retrievals WHERE candidate_id=?',(child_id,)).fetchone()
        if (not parent or not child or parent_id == child_id or data['parent_id'] != parent_id or data['child_id'] != child_id
                or data['parent_digest'] != parent[1] or data['child_digest'] != child[1]
                or _checksum(parent[0]) != parent[1] or _checksum(child[0]) != child[1]
                or parent[2] != 'pending'
                or not isinstance(data['actor'],str) or not data['actor'].strip()
                or not isinstance(data['rationale'],str) or not data['rationale'].strip()):
            raise ValueError('invalid lineage')
        p,c = json.loads(parent[0]),json.loads(child[0])
        sr,lr = data['state_revision'],data['ledger_revision']
        if (any(type(r) is not int or r < 0 for r in (sr,lr))
                or c['state_revision'] != sr or c['ledger_revision'] != lr
                or p['output'] != c['output']
                or sr < p['state_revision'] or lr < p['ledger_revision']
                or (sr,lr) == (p['state_revision'],p['ledger_revision'])
                or db.execute('SELECT 1 FROM retrieval_terminations WHERE candidate_id=?',(parent_id,)).fetchone()):
            raise ValueError('renewal payload/revision mismatch')
        return data,digest
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('renewal integrity mismatch: '+str(exc)) from exc


def verify_renewals(db):
    rows = db.execute('SELECT child_id,parent_id FROM candidate_renewals').fetchall()
    parents = dict(rows)
    for child,_ in rows:
        _link(db,child)
        seen=set()
        node=child
        while node in parents:
            if node in seen:
                raise ValueError('renewal cycle integrity mismatch')
            seen.add(node)
            node=parents[node]


def overlay_renewal(db,candidate):
    incoming = _link(db,candidate.candidate_id)
    if incoming:
        candidate = replace(candidate,review_context=incoming[1],renewal=incoming[0])
        if candidate.termination and candidate.termination['kind'] == 'rejected':
            if candidate.termination['review'].get('candidate_context') != incoming[1]:
                raise ValueError('renewed rejection context integrity mismatch')
    outgoing = db.execute('SELECT child_id FROM candidate_renewals WHERE parent_id=?',(candidate.candidate_id,)).fetchone()
    if outgoing:
        _link(db,outgoing[0])
        if candidate.status != 'pending':
            raise ValueError('renewed parent lifecycle integrity mismatch')
        candidate=replace(candidate,status='superseded',successor_id=outgoing[0])
    return candidate


def renew(queue,parent_id,child_id,*,actor,rationale,expected_state_revision,
          expected_ledger_revision,authorize=None,_fault=None):
    from .pending_retrieval import _read_pending, _decode
    if any(not isinstance(s,str) or not s.strip() for s in (parent_id,child_id,actor,rationale)) or parent_id == child_id:
        raise ValueError('distinct candidate IDs, actor and rationale required')
    if any(type(r) is not int or r < 0 for r in (expected_state_revision,expected_ledger_revision)):
        raise ValueError('expected revisions must be nonnegative integers')
    if not callable(authorize) or authorize(actor,'evidence_renew') is not True:
        raise PermissionError('authenticated renewal authorization required')
    def checkpoint(name):
        if _fault is not None: _fault(name)
    with closing(queue.store._connect()) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            queue._verify(db)
            existing = _link(db,child_id)
            if existing:
                data,_ = existing
                if (data['parent_id'],data['actor'],data['rationale'],data['state_revision'],data['ledger_revision']) != (parent_id,actor,rationale,expected_state_revision,expected_ledger_revision):
                    raise ValueError('renewal request conflict')
                result=_read_pending(db,child_id)
                db.execute('COMMIT')
                return result
            parent=_read_pending(db,parent_id)
            if parent.status != 'pending':
                raise PermissionError('only pending candidates can be renewed')
            if db.execute('SELECT 1 FROM pending_retrievals WHERE candidate_id=?',(child_id,)).fetchone():
                raise ValueError('child candidate ID already exists')
            _,sr,lr,_ = queue.store._verify_integrity(db)
            if (sr,lr) != (expected_state_revision,expected_ledger_revision):
                raise RuntimeError('stale renewal revisions')
            if sr < parent.state_revision or lr < parent.ledger_revision or (sr,lr) == (parent.state_revision,parent.ledger_revision):
                raise ValueError('candidate is not stale against current revisions')
            raw,pdigest=db.execute('SELECT payload,digest FROM pending_retrievals WHERE candidate_id=?',(parent_id,)).fetchone()
            payload=json.loads(raw)
            payload.update(candidate_id=child_id,state_revision=sr,ledger_revision=lr)
            encoded=_encode(payload)
            cdigest=_checksum(encoded)
            _decode((child_id,encoded,cdigest,'pending',None))
            db.execute("INSERT INTO pending_retrievals VALUES (?,?,?,'pending',NULL)",(child_id,encoded,cdigest))
            checkpoint('after_child')
            data=dict(parent_id=parent_id,child_id=child_id,parent_digest=pdigest,child_digest=cdigest,
                      actor=actor,rationale=rationale,state_revision=sr,ledger_revision=lr)
            record=_encode(data)
            db.execute('INSERT INTO candidate_renewals VALUES (?,?,?,?)',(child_id,parent_id,record,_checksum(record)))
            checkpoint('after_lineage')
            queue._verify(db)
            result=_read_pending(db,child_id)
            checkpoint('before_commit')
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction: db.execute('ROLLBACK')
            raise
    checkpoint('after_commit')
    return result
