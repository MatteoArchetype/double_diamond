from claim_disposition import make_disposition, requires_human_review

def test_bounded_claim_is_auditable():
    d=make_disposition("C1","retain_bounded","Direct evidence supports the bounded claim.",["E1"],"provisional","retained_bounded",["EU-only context"],"decision-relevant")
    assert d.evidence_ids == ["E1"]

def test_withdraw_requires_withdrawn_status():
    try: make_disposition("C2","withdraw","Evidence was misread.",["E2"],"retained","retained",[],"high")
    except ValueError: return
    assert False

def test_promotion_requires_hypothesis_status():
    try: make_disposition("C3","promote_to_hypothesis","Suggestive only.",["E3"],"observed","retained",[],"medium")
    except ValueError: return
    assert False

def test_foundational_change_requires_review():
    d=make_disposition("C4","narrow","Evidence limits scope.",["E4"],"retained","qualified",["transferability"],"high")
    assert requires_human_review(d, foundational=True)

def test_unresolved_can_be_evidence_light():
    d=make_disposition("C5","unresolved","Evidence conflicts.",[],"provisional","unresolved",["conflict"],"high")
    assert d.disposition == "unresolved"
