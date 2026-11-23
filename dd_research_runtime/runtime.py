from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
import copy
import datetime as dt
import json

GATED_ACTIONS = {
    'primary_research','sensitive_access','consequential_action',
    'scope_change','material_reframing','phase_transition','publication',
}

class ResearchInvariantError(Exception): pass
class GateRequired(ResearchInvariantError): pass

@dataclass
class ResearchState:
    schema_version: str = '0.2'
    research_id: str = ''
    status: str = 'draft'
    brief: Dict[str, Any] = field(default_factory=dict)
    scope: Dict[str, Any] = field(default_factory=dict)
    research_questions: List[Dict[str, Any]] = field(default_factory=list)
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    evidence: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    claims: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    hypotheses: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    mechanisms: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    contradictions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cases: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    scenarios: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    indicators: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    uncertainties: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    human_gates: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    research_cycles: List[Dict[str, Any]] = field(default_factory=list)
    change_log: List[Dict[str, Any]] = field(default_factory=list)
    outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def _now(self): return dt.datetime.now(dt.timezone.utc).isoformat()
    def _change(self, op, ids, detail=''):
        self.change_log.append({'timestamp': self._now(), 'operation': op, 'ids': ids, 'detail': detail})

    def add_source(self, r):
        sid=r['source_id']
        if sid in self.sources: raise ResearchInvariantError(f'duplicate source: {sid}')
        if not r.get('provenance') or not r.get('independence_cluster'):
            raise ResearchInvariantError('source requires provenance and independence_cluster')
        self.sources[sid]=copy.deepcopy(r); self._change('add_source',[sid])

    def add_evidence(self, r):
        eid=r['evidence_id']; sid=r.get('source_id')
        if eid in self.evidence: raise ResearchInvariantError(f'duplicate evidence: {eid}')
        synthetic=bool(r.get('synthetic',False))
        if not synthetic and sid not in self.sources: raise ResearchInvariantError(f'unknown source: {sid}')
        if not synthetic and not r.get('exact_location'): raise ResearchInvariantError('non-synthetic evidence requires exact_location')
        self.evidence[eid]=copy.deepcopy(r); self._change('add_evidence',[eid])

    def add_claim(self, r):
        cid=r['claim_id']
        if cid in self.claims: raise ResearchInvariantError(f'duplicate claim: {cid}')
        disposition=r.get('disposition','draft'); typ=r.get('claim_type','descriptive')
        eids=r.get('evidence_ids',[])
        if disposition not in {'hypothesis','unresolved','unknown'} and typ in {'causal','generalisation'} and not eids:
            raise ResearchInvariantError('causal/generalisation claim requires evidence or explicit unresolved/hypothesis state')
        missing=[e for e in eids if e not in self.evidence]
        if missing: raise ResearchInvariantError(f'claim references missing evidence: {missing}')
        self.claims[cid]=copy.deepcopy(r); self._change('add_claim',[cid])

    def update_claim(self, cid, patch, reason, cycle_id):
        if cid not in self.claims: raise ResearchInvariantError(f'unknown claim: {cid}')
        old=copy.deepcopy({k:v for k,v in self.claims[cid].items() if k!='belief_history'}); self.claims[cid].update(copy.deepcopy(patch))
        self.claims[cid].setdefault('belief_history',[]).append({'cycle_id':cycle_id,'previous':old,'reason':reason})
        self._change('update_claim',[cid],reason)

    def add_contradiction(self, r):
        xid=r['contradiction_id']
        if xid in self.contradictions: raise ResearchInvariantError(f'duplicate contradiction: {xid}')
        for cid in (r['claim_a'],r['claim_b']):
            if cid not in self.claims: raise ResearchInvariantError(f'contradiction references missing claim: {cid}')
        if r.get('disposition') in {'resolved','narrowed','qualified','withdrawn'} and not r.get('resolution_basis'):
            raise ResearchInvariantError('resolved contradiction requires resolution_basis')
        self.contradictions[xid]=copy.deepcopy(r); self._change('add_contradiction',[xid])

    def add_scenario(self,r):
        sid=r['scenario_id']
        if sid in self.scenarios: raise ResearchInvariantError(f'duplicate scenario: {sid}')
        if r.get('is_forecast') is True: raise ResearchInvariantError('scenario cannot be a forecast')
        if not r.get('assumptions') or not r.get('disconfirming_indicators'):
            raise ResearchInvariantError('scenario requires assumptions and disconfirming_indicators')
        self.scenarios[sid]=copy.deepcopy(r); self._change('add_scenario',[sid])

    def create_gate(self, gate_id, gate_type, proposal, rationale, decision_required):
        if gate_id in self.human_gates: raise ResearchInvariantError(f'duplicate gate: {gate_id}')
        self.human_gates[gate_id]={'gate_id':gate_id,'gate_type':gate_type,'status':'pending_review','proposal':proposal,'rationale':rationale,'decision_required':decision_required}
        self._change('create_gate',[gate_id])

    def approve_gate(self, gate_id):
        g=self.human_gates.get(gate_id)
        if not g or g['status']!='pending_review': raise ResearchInvariantError('only pending gates can be approved')
        g['status']='approved'; self._change('approve_gate',[gate_id])

    def execute_gated(self, gate_id, action):
        if action not in GATED_ACTIONS: return
        g=self.human_gates.get(gate_id)
        if not g or g['status']!='approved': raise GateRequired(f'approved human gate required for: {action}')
        if g.get('gate_type') != action: raise GateRequired(f'human gate type must match action: {action}')
        g['status']='executed'; self._change('execute_gated',[gate_id],action)

    def add_cycle(self, r):
        required={'cycle_id','phase','objective','status'}
        if not required.issubset(r): raise ResearchInvariantError(f'cycle missing: {sorted(required-set(r))}')
        self.research_cycles.append(copy.deepcopy(r)); self._change('add_cycle',[r['cycle_id']])

    def trace_claim(self,cid):
        c=self.claims[cid]; out=[]
        for eid in c.get('evidence_ids',[]):
            e=self.evidence[eid]; s=self.sources.get(e.get('source_id'))
            out.append({'claim_id':cid,'evidence_id':eid,'source_id':e.get('source_id'),'source_title':s.get('title') if s else None,'exact_location':e.get('exact_location'),'independence_cluster':s.get('independence_cluster') if s else None})
        return out

    def validate(self)->Tuple[bool,List[str]]:
        errors=[]
        for eid,e in self.evidence.items():
            if not e.get('synthetic') and e.get('source_id') not in self.sources: errors.append(f'{eid}: missing source')
            if not e.get('synthetic') and not e.get('exact_location'): errors.append(f'{eid}: missing exact location')
        for cid,c in self.claims.items():
            for eid in c.get('evidence_ids',[]):
                if eid not in self.evidence: errors.append(f'{cid}: missing evidence {eid}')
            if c.get('claim_type') in {'causal','generalisation'} and c.get('disposition') not in {'hypothesis','unresolved','unknown'} and not c.get('evidence_ids'):
                errors.append(f'{cid}: causal/generalisation claim lacks evidence')
        for xid,x in self.contradictions.items():
            if x.get('claim_a') not in self.claims or x.get('claim_b') not in self.claims: errors.append(f'{xid}: missing claim reference')
        for sid,s in self.scenarios.items():
            if s.get('is_forecast') is True: errors.append(f'{sid}: scenario marked forecast')
        return (not errors,errors)

    def export(self, path):
        ok,errors=self.validate()
        if not ok: raise ResearchInvariantError('cannot export invalid state: '+json.dumps(errors))
        with open(path,'w',encoding='utf-8') as f: json.dump(self.snapshot(),f,ensure_ascii=False,indent=2)

    def snapshot(self):
        return copy.deepcopy({k:v for k,v in self.__dict__.items()})
