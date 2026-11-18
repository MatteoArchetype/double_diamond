from dataclasses import replace

import pytest
from test_persistent_ingestion import store,batch,auth
from test_retrieval_validation import DOC
from dd_research_runtime.retrieval_validation import validate_retrieval_output,RetrievalValidation
from dd_research_runtime.evidence_review import review_retrieval,ingest_with_review
from dd_research_runtime.runtime import ResearchState
from retrieval_adapter import RetrievedDocument


def validate(**changes):
    return validate_retrieval_output('retrieve',dict(status='completed',documents=[{**DOC,**changes}]))


@pytest.mark.parametrize('field,value',[
    ('source_id', ['unhashable']),('title',None),('publisher',17),('url',True),
    ('retrieved_at',{}),('passage',123),('content_location',False),('provenance',[]),
])
def test_required_fields_reject_wrong_types_without_raising(field,value):
    result=validate(**{field:value})
    assert result.status == 'rejected' and result.documents == ()
    assert result.errors


@pytest.mark.parametrize('value',['false','true',0,1,None,[]])
def test_synthetic_flag_is_not_truthiness(value):
    assert validate(synthetic=value,provenance='synthetic').status == 'rejected'


@pytest.mark.parametrize('provenance',['synthetic','synthetic_test','synthetic-test',' SYNTHETIC '])
def test_synthetic_label_cannot_enter_as_real(provenance):
    assert validate(synthetic=False,provenance=provenance).status == 'rejected'


@pytest.mark.parametrize('provenance',['synthetic','synthetic_test','synthetic-test'])
def test_explicit_synthetic_payload_preserved(provenance):
    result=validate(synthetic=True,provenance=provenance)
    assert result.status == 'ready_for_review'
    payload=result.documents[0].to_evidence_payload()
    assert payload['synthetic'] is True and payload['provenance'] == provenance


@pytest.mark.parametrize('metadata',[None,[],{1:'nonstring key'},{'value':object()},
    {'value':(1,2)},{'value':{1,2}},{'value':float('nan')},{'value':float('inf')},
    {'nested':{'value':float('-inf')}}])
def test_metadata_must_be_faithful_finite_json(metadata):
    result=validate(metadata=metadata)
    assert result.status == 'rejected' and result.documents == ()


def test_circular_and_excessively_deep_metadata_rejected():
    circular={};circular['self']=circular
    assert validate(metadata=circular).status == 'rejected'
    deep={};node=deep
    for _ in range(102):node['next']={};node=node['next']
    assert validate(metadata=deep).status == 'rejected'


def test_shared_values_are_not_confused_with_cycles_and_payload_is_detached():
    shared=[{'a':'æøå','b':None,'c':True,'d':1,'e':1.5}]
    metadata={'first':shared,'second':shared}
    v=validate(metadata=metadata)
    assert v.status == 'ready_for_review'
    payload=v.documents[0].to_evidence_payload()
    payload['metadata']['first'][0]['a']='changed copy'
    assert metadata['first'][0]['a'] == 'æøå'
    assert payload['metadata']['second'][0]['a'] == 'æøå'


@pytest.mark.parametrize('field,value',[('published_at',False),('published_at',''),
    ('independence_cluster',{}),('independence_cluster','  ')])
def test_optional_fields_are_strings_or_none(field,value):
    assert validate(**{field:value}).status == 'rejected'


def test_valid_and_malformed_batch_is_atomic():
    result=validate_retrieval_output('retrieve',dict(status='completed',documents=[DOC,{**DOC,'source_id':[]}]))
    assert result.status == 'rejected' and not result.documents


def test_manual_ready_status_cannot_bypass_source_type_validation():
    doc=RetrievedDocument(**{**DOC,'passage':None})
    forged=RetrievalValidation('ready_for_review',(doc,),())
    with pytest.raises(TypeError):
        review_retrieval(forged,snapshots={'s1':dict(text='anything',location='section 2')},
                         reviewer='human',decision='approved',rationale='Check')


def test_post_review_metadata_mutation_cannot_enter_durable_state(store):
    v,r=batch()
    v.documents[0].metadata['unsafe']=object()
    with pytest.raises(TypeError):
        store.ingest(v,r,operation_id='mutated',expected_state_revision=0,expected_ledger_revision=0,authorize=auth)
    assert store.load()[1] == store.ledger.revision() == 0
    assert store.review_coverage()['retained_reviews'] == 0


def test_valid_typed_metadata_survives_durable_roundtrip(store):
    v,_=batch()
    metadata={'sample':{'null':None,'boolean':False,'count':2,'score':0.25,'labels':['one','two']}}
    v=replace(v,documents=(replace(v.documents[0],metadata=metadata),))
    r=review_retrieval(v,snapshots={'s1':dict(text='Exact passage s1',location='p1')},
                       reviewer='human',decision='approved',rationale='Checked fixture')
    store.ingest(v,r,operation_id='typed',expected_state_revision=0,expected_ledger_revision=0,authorize=auth)
    assert store.load()[0].evidence['s1']['metadata']['sample'] == metadata['sample']
    assert store.load_review('typed')['documents'][0]['metadata']['sample'] == metadata['sample']


def test_synthetic_conflict_cannot_use_direct_ingestion_with_old_review():
    v,r=batch()
    changed=replace(v,documents=(replace(v.documents[0],synthetic=False,provenance='synthetic'),))
    state=ResearchState()
    with pytest.raises(ValueError,match='synthetic'):ingest_with_review(state,changed,r,authorize=auth)
    assert not state.evidence and not state.sources
