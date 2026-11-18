"""Open research questions are advisory records, not evidence or human decisions."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from dd_research_runtime.local_app import Workspace,ACTOR,_authorize
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from test_local_app import create,request,source
from test_frame_revision import prepare_workspace,transition

@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w)
    request(w,cid,'source',source(),request_id='fixture')
    for rid in ('first','second'):
        request(w,cid,'claim',dict(claim='Invented '+rid,claim_type='descriptive',evidence_ids=['synthetic-fixture'],rationale='Fixture only'),request_id=rid)
    return w,cid


def gap(**changes):
    value=dict(question='Does this invented observation transfer?',claim_ids=['claim-first'],rationale='Record an explicit fixture gap');value.update(changes);return value


def test_question_and_selected_claim_links_are_one_durable_advisory_transaction(case):
    w,cid=case;before=w.view(cid)
    request(w,cid,'uncertainty',gap(),request_id='gap')
    after=Workspace(w.path).view(cid);uid='uncertainty-gap'
    assert after['revision']==before['revision']+1 and after['ledger_revision']==before['ledger_revision']
    assert after['state']['uncertainties'][uid]==dict(uncertainty_id=uid,question=gap()['question'],status='open')
    assert after['state']['claims']['claim-first']['material_uncertainties']==[uid]
    assert 'material_uncertainties' not in after['state']['claims']['claim-second']
    assert after['state']['claims']['claim-first']['status']=='draft'
    assert after['state']['claims']['claim-first']['analysis_status']=='advisory'
    for key in ('evidence','sources','human_gates','workflow'):assert after['state'][key]==before['state'][key]
    audit=w.store(cid).load_analysis_operation('ui-gap')
    assert len(audit['request']['commands'])==2


def test_unlinked_question_can_precede_interpretation_and_define_selection(case):
    w,cid=case;request(w,cid,'uncertainty',gap(claim_ids=[]),request_id='standalone')
    uid='uncertainty-standalone'
    assert all(uid not in c.get('material_uncertainties',[]) for c in w.view(cid)['state']['claims'].values())
    request(w,cid,'claim',dict(claim='A new tentative interpretation',claim_type='causal',evidence_ids=[],uncertainty_ids=[uid],rationale='Explicit gap link, still unresolved'),request_id='later')
    claim=w.view(cid)['state']['claims']['claim-later']
    assert claim['material_uncertainties']==[uid] and claim['evidence_origin']=='none' and claim['disposition']=='unresolved'
    request(w,cid,'phase_record',dict(record=dict(evidence_ids=['synthetic-fixture'],notes='Invented observations',perspectives=['Invented observer','Unstudied perspectives'],limitations='Synthetic only'),rationale='Fixture'))
    transition(w,cid,'define')
    request(w,cid,'phase_record',dict(record=dict(problem='Bound the invented interpretation',claim_ids=['claim-later'],uncertainty_ids=[uid],success_criteria=['Retain the unresolved question']),rationale='Explicit frame selection'))
    assert w.view(cid)['state']['workflow']['records']['define']['uncertainty_ids']==[uid]


def test_additional_uncertainties_preserve_existing_links(case):
    w,cid=case
    for rid in ('one','two'):request(w,cid,'uncertainty',gap(claim_ids=['claim-first','claim-second']),request_id=rid)
    for claim in w.view(cid)['state']['claims'].values():assert claim['material_uncertainties']==['uncertainty-one','uncertainty-two']

@pytest.mark.parametrize('changes',[
    {'question':''},{'question':True},{'rationale':''},{'claim_ids':['missing']},{'claim_ids':['claim-first','claim-first']},
    {'claim_ids':'claim-first'},{'claim_ids':[True]},{'status':'resolved'},{'resolution_basis':'Invented approval'},
    {'evidence_ids':['synthetic-fixture']},{'gate_id':'inferred'},{'uncertainty_id':'overwrite'},{'claim_ids':None}])
def test_invalid_question_has_no_partial_links_or_state(case,changes):
    w,cid=case;before=w.view(cid)
    with pytest.raises((ValueError,TypeError)):request(w,cid,'uncertainty',gap(**changes))
    assert w.view(cid)==before

@pytest.mark.parametrize('ids',[['missing'],['uncertainty-gap','uncertainty-gap'],'uncertainty-gap',[False]])
def test_new_interpretation_rejects_invalid_uncertainty_links(case,ids):
    w,cid=case;request(w,cid,'uncertainty',gap(),request_id='gap');before=w.view(cid)
    with pytest.raises(ValueError):request(w,cid,'claim',dict(claim='Invalid links',claim_type='descriptive',evidence_ids=[],uncertainty_ids=ids,rationale='Fixture'))
    assert w.view(cid)==before

@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit'])
def test_interrupted_save_rolls_back_question_and_all_claim_links(case,monkeypatch,phase):
    w,cid=case;before=w.view(cid);original=PersistentEvidenceStore.apply_analysis
    def wrapped(self,*args,**kwargs):
        def fault(name):
            if name==phase:raise RuntimeError('simulated interruption')
        return original(self,*args,**kwargs,_fault=fault)
    monkeypatch.setattr(PersistentEvidenceStore,'apply_analysis',wrapped)
    with pytest.raises(RuntimeError):request(w,cid,'uncertainty',gap(claim_ids=['claim-first','claim-second']))
    assert w.view(cid)==before


def test_concurrent_tabs_cannot_create_an_orphan_question_or_overwrite_links(case):
    w,cid=case;before=w.view(cid)
    def save(i):
        try:return request(w,cid,'uncertainty',gap(question='Invented gap '+str(i)),request_id='parallel-'+str(i),expected_revision=before['revision'],expected_ledger_revision=before['ledger_revision'])
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,range(2)))
    assert sum(r is not None for r in results)==1
    after=w.view(cid);assert len(after['state']['uncertainties'])==1 and after['revision']==before['revision']+1
    assert after['state']['claims']['claim-first']['material_uncertainties']==list(after['state']['uncertainties'])


def test_refuses_analysis_permission_failure(case,monkeypatch):
    from dd_research_runtime import local_app
    w,cid=case;before=w.view(cid);monkeypatch.setattr(local_app,'_authorize',lambda actor,capability:False)
    with pytest.raises(PermissionError):request(w,cid,'uncertainty',gap())
    assert w.view(cid)==before


def test_existing_uncertainty_identifier_cannot_be_overwritten(case):
    w,cid=case;before=w.view(cid)
    w.store(cid).apply_analysis([dict(type='put_uncertainty',record=dict(uncertainty_id='uncertainty-collision',question='Existing retained question',status='open'))],operation_id='retained-gap',actor=ACTOR,rationale='Fixture',expected_state_revision=before['revision'],authorize=_authorize)
    before=w.view(cid)
    with pytest.raises(ValueError,match='already exists'):request(w,cid,'uncertainty',gap(),request_id='collision')
    assert w.view(cid)==before


def test_new_gap_stales_report_but_preserves_original_define_context_and_checkpoint(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=prepare_workspace(w);before=w.view(cid)
    original=w.visit(cid,'V2');request(w,cid,'uncertainty',gap(claim_ids=['claim-interpretation']),request_id='later-gap')
    after=w.view(cid);uid='uncertainty-later-gap'
    assert after['state']['workflow']==before['state']['workflow'] and after['state']['human_gates']==before['state']['human_gates']
    assert after['state']['workflow']['status']=='stopped' and not any(r['current'] for r in after['reports'])
    historical=w.visit(cid,'V2');assert historical['visit']==original['visit'] and historical['context']==original['context']
    assert uid not in historical['visit']['record']['uncertainty_ids']
    data,_=w.backup(cid,after['revision']);preview=w.inspect_backup(data);restored=w.restore_backup(data,preview['checkpoint_digest'])
    assert w.view(restored['case_id'])['state']==after['state'] and not restored['approval_granted']


def test_stale_uncertainty_submission_is_refused(case):
    w,cid=case;before=w.view(cid);request(w,cid,'uncertainty',gap(),request_id='one');after=w.view(cid)
    with pytest.raises(RuntimeError):request(w,cid,'uncertainty',gap(),request_id='two',expected_revision=before['revision'])
    assert w.view(cid)==after


def test_question_link_limit_is_bounded_and_atomic(case):
    w,cid=case;before=w.view(cid)
    with pytest.raises(ValueError,match='at most 99'):request(w,cid,'uncertainty',gap(claim_ids=['C'+str(i) for i in range(100)]))
    assert w.view(cid)==before


def test_ninety_nine_links_fit_the_existing_hundred_command_transaction(case):
    w,cid=case;before=w.view(cid)
    commands=[dict(type='add_claim',record=dict(claim_id='C'+str(i),claim='Invented interpretation '+str(i),disposition='unresolved',status='draft',evidence_ids=[])) for i in range(97)]
    w.store(cid).apply_analysis(commands,operation_id='many-fixture-claims',actor=ACTOR,rationale='Bounded fixture only',expected_state_revision=before['revision'],authorize=_authorize)
    ids=list(w.view(cid)['state']['claims']);assert len(ids)==99
    request(w,cid,'uncertainty',gap(claim_ids=ids),request_id='bounded')
    after=w.view(cid)
    assert all('uncertainty-bounded' in c.get('material_uncertainties',[]) for c in after['state']['claims'].values())
