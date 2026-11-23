from dd_research_runtime.runtime import ResearchState, ResearchInvariantError, GateRequired


def test_minimum_export_contract():
    s=ResearchState(research_id='r1')
    required={'schema_version','research_id','status','brief','scope','research_questions','sources','evidence','claims','hypotheses','contradictions','mechanisms','cases','scenarios','indicators','uncertainties','human_gates','research_cycles','change_log','outputs'}
    assert required <= set(s.snapshot())


def test_traceability_and_independence():
    s=ResearchState(research_id='r1')
    s.add_source({'source_id':'S1','title':'Test','provenance':'publisher','independence_cluster':'C1'})
    s.add_evidence({'evidence_id':'E1','source_id':'S1','exact_location':'p.4','finding':'x'})
    s.add_claim({'claim_id':'C1','claim_type':'descriptive','disposition':'retained','claim':'x','evidence_ids':['E1']})
    t=s.trace_claim('C1')
    assert t[0]['source_id']=='S1' and t[0]['exact_location']=='p.4'


def test_non_synthetic_location_required():
    s=ResearchState()
    s.add_source({'source_id':'S1','title':'Test','provenance':'publisher','independence_cluster':'C1'})
    try: s.add_evidence({'evidence_id':'E1','source_id':'S1'})
    except ResearchInvariantError: return
    raise AssertionError('expected this call to be rejected')


def test_contradiction_preserved():
    s=ResearchState()
    for cid in ['A','B']:
        s.add_claim({'claim_id':cid,'claim_type':'descriptive','disposition':'retained','claim':cid})
    s.add_contradiction({'contradiction_id':'X1','claim_a':'A','claim_b':'B','disposition':'unresolved'})
    assert 'X1' in s.contradictions


def test_scenario_not_forecast():
    s=ResearchState()
    try: s.add_scenario({'scenario_id':'S','is_forecast':True,'assumptions':['a'],'disconfirming_indicators':['i']})
    except ResearchInvariantError: return
    raise AssertionError('expected this call to be rejected')


def test_gate_blocks_and_then_allows():
    s=ResearchState()
    s.create_gate('G1','primary_research','interview people','need primary evidence','approve access')
    try: s.execute_gated('G1','primary_research')
    except GateRequired: pass
    else: raise AssertionError('expected this call to be rejected')
    s.approve_gate('G1'); s.execute_gated('G1','primary_research')
    assert s.human_gates['G1']['status']=='executed'


def test_belief_history():
    s=ResearchState()
    s.add_claim({'claim_id':'C1','claim_type':'descriptive','disposition':'retained','claim':'old'})
    s.update_claim('C1',{'claim':'new','confidence':'medium'},'new evidence','cycle-1')
    assert s.claims['C1']['belief_history'][0]['previous']['claim']=='old'


if __name__=='__main__':
    tests=[v for k,v in globals().items() if k.startswith('test_')]
    for t in tests: t()
    print(f'{len(tests)}/{len(tests)} tests passed')


def test_synthetic_evidence_stays_marked():
    from dd_research_runtime.adapters import EvidenceAdapter, EvidenceCandidate, RetrievedDocument
    s=ResearchState()
    a=EvidenceAdapter(s)
    d=RetrievedDocument('SYN1','Synthetic fixture','test','fixture://syn','now','x',{'kind':'synthetic'},'SYNTHETIC',True)
    a.ingest_document_findings(d,[EvidenceCandidate('E-SYN','SYN1','fixture finding','fixture line 1',synthetic=True)])
    assert s.sources['SYN1']['synthetic'] is True
    assert s.evidence['E-SYN']['synthetic'] is True


def test_real_evidence_requires_location_and_known_source():
    from dd_research_runtime.adapters import EvidenceAdapter, EvidenceCandidate, RetrievedDocument
    s=ResearchState(); a=EvidenceAdapter(s)
    try: a.ingest([EvidenceCandidate('E1','UNKNOWN','x','p.1')])
    except ResearchInvariantError: pass
    else: raise AssertionError('expected this call to be rejected')
    d=RetrievedDocument('S1','Real','Publisher','https://example.org','now','body',{'kind':'publisher'},'P1',False)
    try: a.ingest_document_findings(d,[EvidenceCandidate('E2','S1','x','')])
    except ResearchInvariantError: return
    raise AssertionError('expected this call to be rejected')


def test_duplicate_evidence_is_idempotent():
    from dd_research_runtime.adapters import EvidenceAdapter, EvidenceCandidate, RetrievedDocument
    s=ResearchState(); a=EvidenceAdapter(s)
    d=RetrievedDocument('S1','Real','Publisher','https://example.org','now','body',{'kind':'publisher'},'P1')
    c=EvidenceCandidate('','S1','same finding','p.2')
    first=a.ingest_document_findings(d,[c]); second=a.ingest_document_findings(d,[c])
    assert first == second and len(s.evidence)==1
