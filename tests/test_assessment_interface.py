"""Evidence-fit assessments remain advisory and exact-version-bound; fixtures only."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from assessment import DIMENSIONS
from dd_research_runtime.local_app import Workspace,ACTOR,_authorize
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from test_local_app import create,request,source
from test_frame_revision import prepare_workspace

@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w)
    request(w,cid,'source',source(),request_id='fixture')
    request(w,cid,'source',source(title='Other invented source',url='https://example.org/other',passage='Other invented passage.',snapshot='Context. Other invented passage. Context.'),request_id='other')
    request(w,cid,'claim',dict(claim='Synthetic bounded interpretation',claim_type='descriptive',evidence_ids=['synthetic-fixture'],rationale='Fixture only'),request_id='interpretation')
    return w,cid


def assessment(**changes):
    value=dict(claim_id='claim-interpretation',evidence_id='synthetic-fixture',dimensions={key:'unknown' for key in DIMENSIONS},limitations=['Invented material only'],rationale='Record unknown evidence fit without inferring a conclusion');value.update(changes);return value


def test_advisory_assessment_is_durable_and_does_not_accept_claim_or_change_source(case):
    w,cid=case;before=w.view(cid);assert before['assessment_dimensions']==list(DIMENSIONS)
    request(w,cid,'assessment',assessment(),request_id='fit')
    after=Workspace(w.path).view(cid);assert after['revision']==before['revision']+1 and after['ledger_revision']==before['ledger_revision']
    a=after['assessments'][0];assert a['current'] and a['assessment']['dimensions']==assessment()['dimensions']
    assert a['assessment']['status']=='advisory' and a['assessment']['evidence_origin']=='synthetic_only'
    for key in ('claims','evidence','sources','human_gates','workflow','uncertainties','contradictions'):assert after['state'][key]==before['state'][key]
    assert w.store(cid).load_analysis_operation('ui-fit')['request']['commands'][0]['type']=='assess_evidence'
    data,_=w.backup(cid,after['revision']);preview=w.inspect_backup(data);restored=w.restore_backup(data,preview['checkpoint_digest'])
    assert w.view(restored['case_id'])['state']==after['state'] and w.view(restored['case_id'])['assessments']==after['assessments']
    assert not restored['approval_granted']

@pytest.mark.parametrize('change',[
    {'claim_id':'missing'},{'evidence_id':'missing'},{'evidence_id':'synthetic-other'},{'claim_id':[]},
    {'dimensions':{}},{'dimensions':[]},{'dimensions':{**{k:'unknown' for k in DIMENSIONS},'score':'high'}},
    {'dimensions':{**{k:'unknown' for k in DIMENSIONS},'strength':'excellent'}},
    {'dimensions':{**{k:'unknown' for k in DIMENSIONS},'strength':True}},
    {'limitations':'none'},{'limitations':['']},{'limitations':[True]},{'rationale':''},
    {'status':'accepted'},{'gate_id':'inferred'},{'assessor':'authenticated-human'},{'assessment_id':'overwrite'},{'overall_score':100}])
def test_invalid_or_consequential_assessment_fields_have_no_partial_effect(case,change):
    w,cid=case;before=w.view(cid)
    with pytest.raises((ValueError,TypeError)):request(w,cid,'assessment',assessment(**change))
    assert w.view(cid)==before

@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit'])
def test_interrupted_assessment_leaves_neither_record_nor_audit_change(case,phase,monkeypatch):
    w,cid=case;before=w.view(cid);original=PersistentEvidenceStore.apply_analysis
    def wrapped(self,*args,**kwargs):
        def fault(name):
            if name==phase:raise RuntimeError('simulated interruption')
        return original(self,*args,**kwargs,_fault=fault)
    monkeypatch.setattr(PersistentEvidenceStore,'apply_analysis',wrapped)
    with pytest.raises(RuntimeError):request(w,cid,'assessment',assessment())
    assert w.view(cid)==before


def test_changed_interpretation_or_uncertainty_link_stales_old_assessment_without_rewriting_it(case):
    w,cid=case;request(w,cid,'assessment',assessment(),request_id='fit');before=w.view(cid)
    record=copy.deepcopy(before['assessments'][0]['assessment'])
    request(w,cid,'uncertainty',dict(question='Does this invented observation transfer?',claim_ids=['claim-interpretation'],rationale='Fixture gap'),request_id='gap')
    after=w.view(cid);assert not after['assessments'][0]['current'] and after['assessments'][0]['assessment']==record
    assert after['state']['evidence']==before['state']['evidence']
    request(w,cid,'assessment',assessment(rationale='Explicit reassessment after changed interpretation context'),request_id='recheck')
    entries={a['assessment']['assessment_id']:a for a in w.view(cid)['assessments']}
    assert not entries['assessment-fit']['current'] and entries['assessment-recheck']['current']


def test_concurrent_stale_tabs_cannot_silently_duplicate_assessment(case):
    w,cid=case;before=w.view(cid)
    def save(i):
        try:return request(w,cid,'assessment',assessment(),request_id='parallel-'+str(i),expected_revision=before['revision'],expected_ledger_revision=before['ledger_revision'])
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,range(2)))
    assert sum(r is not None for r in results)==1
    after=w.view(cid);assert len(after['assessments'])==1 and after['revision']==before['revision']+1


def test_assessment_authorization_and_collision_refusal(case,monkeypatch):
    from dd_research_runtime import local_app
    w,cid=case;request(w,cid,'assessment',assessment(),request_id='saved');before=w.view(cid)
    with pytest.raises((ValueError,RuntimeError)):request(w,cid,'assessment',assessment(rationale='Attempted overwrite'),request_id='saved')
    assert w.view(cid)==before
    monkeypatch.setattr(local_app,'_authorize',lambda actor,capability:False)
    with pytest.raises(PermissionError):request(w,cid,'assessment',assessment())
    assert w.view(cid)==before


def test_report_freshness_is_snapshot_bound_after_current_claim_changes(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=prepare_workspace(w)
    payload=assessment(evidence_id='synthetic-synthetic-source')
    before=w.view(cid);request(w,cid,'assessment',payload,request_id='report-fit')
    after=w.view(cid);assert after['state']['workflow']==before['state']['workflow'] and after['state']['human_gates']==before['state']['human_gates']
    request(w,cid,'report',dict(rationale='Retain advisory assessment in a synthetic report'),request_id='with-fit')
    original=copy.deepcopy(w.view(cid)['state']['outputs']['report-with-fit']);assert original['assessments'][0]['current']
    sr=w.view(cid)['revision'];w.store(cid).apply_analysis([dict(type='update_claim',claim_id='claim-interpretation',patch=dict(claim='Later bounded fixture text'))],operation_id='later-claim-edit',actor=ACTOR,rationale='Fixture',expected_state_revision=sr,authorize=_authorize)
    current=w.view(cid);assert not current['assessments'][0]['current']
    assert current['state']['outputs']['report-with-fit']==original
    assert not any(r['current'] for r in current['reports'])
    request(w,cid,'report',dict(rationale='Show existing assessment already stale at creation'),request_id='with-stale-fit')
    assert not w.view(cid)['state']['outputs']['report-with-stale-fit']['assessments'][0]['current']


def test_viewing_and_mutating_detached_assessment_view_cannot_write_research(case):
    w,cid=case;request(w,cid,'assessment',assessment(),request_id='fit');before=w.view(cid)
    detached=w.view(cid);detached['assessments'][0]['assessment']['dimensions']['strength']='high'
    assert w.view(cid)==before


def test_high_ratings_do_not_promote_a_claim_and_empty_limits_do_not_imply_acceptance(case):
    w,cid=case;before=w.view(cid)
    request(w,cid,'assessment',assessment(dimensions={key:'high' for key in DIMENSIONS},limitations=[]))
    after=w.view(cid);assert after['state']['claims']==before['state']['claims'] and after['state']['human_gates']==before['state']['human_gates']
    assert after['assessments'][0]['assessment']['limitations']==[]
