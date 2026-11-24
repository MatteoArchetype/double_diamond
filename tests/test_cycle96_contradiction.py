from contradiction import assess_contradiction, contradiction_consequence

def test_requires_multiple_items():
    try: assess_contradiction('X1','C1',['E1'],'issue','same','unresolved','material','retrieve',['created'])
    except ValueError: return
    raise AssertionError('expected this call to be rejected')

def test_unresolved_blocks_unqualified():
    a=assess_contradiction('X2','C2',['E2','E3'],'Different outcomes','partially comparable','unresolved','Claim could change','targeted retrieval',['created','reviewed'])
    assert contradiction_consequence(a)=='claim_cannot_be_unqualified'

def test_context_difference_requires_qualification():
    a=assess_contradiction('X3','C3',['E4','E5'],'Different effects','different contexts','context_difference','Transferability limited','bound claim',['created','compared'])
    assert contradiction_consequence(a)=='claim_must_be_bounded_or_qualified'

def test_audit_preserved():
    a=assess_contradiction('X4','C4',['E6','E7'],'Conflict','comparable','material_difference','major implication','human review',['created','context retrieved','human flagged'])
    assert len(a.audit_trail)==3
