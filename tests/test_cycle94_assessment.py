from assessment import assess, decision_relevance
D={"strength":"high","directness":"high","causal_attribution":"low","transferability":"medium","independence":"high","recency":"high","context_completeness":"high","claim_fitness":"high","selection_risk":"medium","baseline_quality":"low","outcome_validity":"medium","systemic_relevance":"low"}
def test_source_quality_is_not_claim_fitness():
 a=assess("E1","C1",{**D,"claim_fitness":"low"},["Authoritative source but not directly about this claim."],"Authoritative source; weak direct fit."); assert decision_relevance(a)=="insufficient_for_unqualified_claim"
def test_causal_limitation_requires_qualification():
 a=assess("E2","C2",D,["Observational evidence; concurrent transformation."],"Direct observation without causal identification."); assert decision_relevance(a)=="usable_with_qualification"
def test_unknown_independence_blocks_unqualified_use():
 a=assess("E3","C3",{**D,"independence":"unknown"},[],"Independence could not be established."); assert decision_relevance(a)=="insufficient_for_unqualified_claim"
