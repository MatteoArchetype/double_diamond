"""Advisory revisions preserve prior versions and cannot make claim decisions."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from dd_research_runtime.local_app import Workspace,ACTOR,_authorize
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from test_local_app import create,request,source
from test_frame_revision import prepare_workspace
from assessment import DIMENSIONS

@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w)
    for rid in ('first','second'):request(w,cid,'source',source(title='Invented '+rid,url='https://example.org/'+rid,passage='Invented '+rid+'.',snapshot='Context. Invented '+rid+'. Context.'),request_id=rid)
    request(w,cid,'claim',dict(claim='Original synthetic interpretation',claim_type='descriptive',evidence_ids=['synthetic-first'],rationale='Fixture'),request_id='interpretation')
    request(w,cid,'uncertainty',dict(question='An explicit fixture gap?',claim_ids=[],rationale='Fixture'),request_id='gap')
    return w,cid


def revision(**changes):
    value=dict(claim_id='claim-interpretation',claim='Revised bounded synthetic interpretation',evidence_ids=['synthetic-second'],uncertainty_ids=['uncertainty-gap'],rationale='Explicit fixture revision');value.update(changes);return value


def test_revision_retains_previous_wording_links_and_fixed_decision_fields(case):
    w,cid=case;before=w.view(cid);assert 'claim-interpretation' in before['revisable_claim_ids']
    request(w,cid,'claim_revision',revision(),request_id='revision')
    after=Workspace(w.path).view(cid);old=before['state']['claims']['claim-interpretation'];new=after['state']['claims']['claim-interpretation']
    assert new['claim']==revision()['claim'] and new['evidence_ids']==['synthetic-second'] and new['material_uncertainties']==['uncertainty-gap']
    for key in ('claim_id','claim_type','status','disposition'):assert new[key]==old[key]
    assert new['analysis_status']=='advisory' and new['evidence_origin']=='synthetic_only'
    assert new['belief_history'][-1]['previous']=={k:v for k,v in old.items() if k!='belief_history'}
    assert new['belief_history'][-1]['reason']==revision()['rationale']
    assert after['revision']==before['revision']+1 and after['ledger_revision']==before['ledger_revision']
    for key in ('evidence','sources','human_gates','workflow','uncertainties'):assert after['state'][key]==before['state'][key]
    data,_=w.backup(cid,after['revision']);preview=w.inspect_backup(data);restored=w.restore_backup(data,preview['checkpoint_digest'])
    assert w.view(restored['case_id'])['state']==after['state'] and not restored['approval_granted']

@pytest.mark.parametrize('change',[
    {'claim_id':'missing'},{'claim_id':True},{'claim':''},{'rationale':''},{'evidence_ids':['missing']},
    {'evidence_ids':['synthetic-first','synthetic-first']},{'uncertainty_ids':['missing']},{'uncertainty_ids':['uncertainty-gap','uncertainty-gap']},
    {'uncertainty_ids':'uncertainty-gap'},{'status':'retained'},{'disposition':'retain_bounded'},{'claim_type':'causal'},
    {'gate_id':'inferred'},{'confidence':'certain'},{'belief_history':[]},{'assessment_id':'inferred'}])
def test_invalid_revision_cannot_partially_change_claim_or_decision(case,change):
    w,cid=case;before=w.view(cid)
    with pytest.raises((ValueError,TypeError)):request(w,cid,'claim_revision',revision(**change))
    assert w.view(cid)==before

@pytest.mark.parametrize('status,disposition',[
    ('retained','retain_bounded'),('qualified','qualify'),('narrowed','narrow'),('withdrawn','withdraw'),
    ('retracted','withdraw'),('hypothesis','promote_to_hypothesis')])
def test_non_draft_decision_records_are_not_revisable_through_this_form(case,status,disposition):
    w,cid=case
    # A verified adopted fixture state supplies decision statuses; no actual human approval.
    from dd_research_runtime.runtime import ResearchState
    import json
    import uuid
    new_cid=uuid.uuid4().hex;folder=w.path/new_cid;folder.mkdir()
    state=ResearchState(research_id='Decision-status fixture');state.claims['C1']=dict(claim_id='C1',claim='Decision record fixture',claim_type='descriptive',evidence_ids=[],status=status,disposition=disposition,analysis_status='advisory')
    # Use a normal case's workflow so the read-only browser guidance can inspect it.
    state.workflow=copy.deepcopy(w.store(cid).load()[0].workflow)
    PersistentEvidenceStore(folder/'research.sqlite').initialize(state)
    (folder/'case-info.json').write_text(json.dumps(dict(title='Decision fixture',synthetic_example=True)))
    before=w.view(new_cid);assert 'C1' not in before['revisable_claim_ids']
    with pytest.raises(PermissionError):request(w,new_cid,'claim_revision',revision(claim_id='C1',evidence_ids=[],uncertainty_ids=[]))
    assert w.view(new_cid)==before

@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit'])
def test_interrupted_revision_cannot_lose_previous_version(case,phase,monkeypatch):
    w,cid=case;before=w.view(cid);original=PersistentEvidenceStore.apply_analysis
    def wrapped(self,*args,**kwargs):
        def fault(name):
            if name==phase:raise RuntimeError('simulated interruption')
        return original(self,*args,**kwargs,_fault=fault)
    monkeypatch.setattr(PersistentEvidenceStore,'apply_analysis',wrapped)
    with pytest.raises(RuntimeError):request(w,cid,'claim_revision',revision())
    assert w.view(cid)==before


def test_concurrent_stale_revisions_do_not_merge_or_overwrite_history(case):
    w,cid=case;before=w.view(cid)
    def save(i):
        try:return request(w,cid,'claim_revision',revision(claim='Concurrent fixture '+str(i)),request_id='parallel-'+str(i),expected_revision=before['revision'],expected_ledger_revision=before['ledger_revision'])
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,range(2)))
    assert sum(r is not None for r in results)==1
    after=w.view(cid);assert after['revision']==before['revision']+1
    assert len(after['state']['claims']['claim-interpretation']['belief_history'])==1
    with pytest.raises(RuntimeError):request(w,cid,'claim_revision',revision(),expected_revision=before['revision'])
    assert w.view(cid)==after


def test_revision_authorization_is_required(case,monkeypatch):
    from dd_research_runtime import local_app
    w,cid=case;before=w.view(cid);monkeypatch.setattr(local_app,'_authorize',lambda actor,capability:False)
    with pytest.raises(PermissionError):request(w,cid,'claim_revision',revision())
    assert w.view(cid)==before


def test_revision_stales_assessment_and_report_but_preserves_original_visit_context(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=prepare_workspace(w);original=w.visit(cid,'V2')
    request(w,cid,'assessment',dict(claim_id='claim-interpretation',evidence_id='synthetic-synthetic-source',dimensions={k:'unknown' for k in DIMENSIONS},limitations=['Fixture'],rationale='Fixture'),request_id='fit')
    request(w,cid,'report',dict(rationale='Fixture report before revision'),request_id='before-revision');before=w.view(cid)
    report=copy.deepcopy(before['state']['outputs']['report-before-revision']);assert before['assessments'][0]['current']
    request(w,cid,'claim_revision',revision(evidence_ids=['synthetic-synthetic-source'],uncertainty_ids=['linked-gap']))
    after=w.view(cid);assert not after['assessments'][0]['current'] and not any(r['current'] for r in after['reports'])
    assert after['state']['outputs']['report-before-revision']==report
    assert after['state']['workflow']==before['state']['workflow'] and after['state']['human_gates']==before['state']['human_gates']
    historical=w.visit(cid,'V2');assert historical['visit']==original['visit'] and historical['context']==original['context']
    assert after['currency']['define'] is False


def test_explicit_empty_links_do_not_invent_support_or_resolve_uncertainty(case):
    w,cid=case;request(w,cid,'claim_revision',revision(evidence_ids=[],uncertainty_ids=[]))
    v=w.view(cid);c=v['state']['claims']['claim-interpretation']
    assert c['evidence_ids']==[] and c['material_uncertainties']==[] and c['evidence_origin']=='none'
    assert v['state']['uncertainties']['uncertainty-gap']['status']=='open'
