"""Unresolved advisory disagreements; all passages and decisions are fixtures."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from dd_research_runtime.local_app import Workspace,ACTOR,_authorize
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.reporting import render_markdown
from test_local_app import create,request,source
from test_frame_revision import prepare_workspace

@pytest.fixture
def case(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w)
    request(w,cid,'source',source(),request_id='synthetic')
    # A non-synthetic flag exercises origin preservation, not actual source acquisition.
    request(w,cid,'source',source(title='Non-synthetic flag fixture',synthetic=False,url='https://example.org/other-fixture',passage='Different invented passage.',snapshot='Context. Different invented passage. Context.'),request_id='source-flag')
    for rid,eids in [('first',['synthetic-synthetic']),('second',['source-source-flag'])]:
        request(w,cid,'claim',dict(claim='Invented interpretation '+rid,claim_type='descriptive',evidence_ids=eids,rationale='Fixture only'),request_id=rid)
    return w,cid


def disagreement(**changes):
    value=dict(claim_a='claim-first',claim_b='claim-second',issue='The invented explanations disagree about the same observation.',rationale='Preserve an unresolved fixture tension');value.update(changes);return value


def test_save_is_durable_advisory_and_preserves_both_sides_and_origins(case):
    w,cid=case;before=w.view(cid);request(w,cid,'contradiction',disagreement(),request_id='tension')
    after=Workspace(w.path).view(cid);r=after['state']['contradictions']['contradiction-tension']
    assert r==dict(contradiction_id='contradiction-tension',claim_a='claim-first',claim_b='claim-second',issue=disagreement()['issue'],disposition='unresolved')
    assert after['revision']==before['revision']+1 and after['ledger_revision']==before['ledger_revision']
    for key in ('claims','sources','evidence','human_gates','workflow','uncertainties'):assert after['state'][key]==before['state'][key]
    assert after['state']['claims']['claim-first']['evidence_origin']=='synthetic_only'
    assert after['state']['claims']['claim-second']['evidence_origin']=='non_synthetic'
    audit=w.store(cid).load_analysis_operation('ui-tension');assert len(audit['request']['commands'])==1
    data,_=w.backup(cid,after['revision']);preview=w.inspect_backup(data);restored=w.restore_backup(data,preview['checkpoint_digest'])
    assert w.view(restored['case_id'])['state']==after['state'] and not restored['approval_granted']

@pytest.mark.parametrize('change',[
    {'claim_a':'claim-second'},{'claim_a':'missing'},{'claim_b':'missing'},{'claim_a':''},{'claim_b':None},
    {'claim_a':['claim-first']},{'issue':''},{'issue':True},{'rationale':''},{'rationale':False},
    {'disposition':'resolved'},{'resolution_basis':'Assumed winner'},{'status':'approved'},
    {'gate_id':'inferred'},{'evidence_ids':['synthetic-synthetic']},{'contradiction_id':'overwrite'}])
def test_invalid_or_consequential_fields_cannot_mutate(case,change):
    w,cid=case;before=w.view(cid)
    with pytest.raises((ValueError,TypeError)):request(w,cid,'contradiction',disagreement(**change))
    assert w.view(cid)==before

@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit'])
def test_interruption_cannot_leave_a_partial_disagreement(case,phase,monkeypatch):
    w,cid=case;before=w.view(cid);original=PersistentEvidenceStore.apply_analysis
    def wrapped(self,*args,**kwargs):
        def fault(name):
            if name==phase:raise RuntimeError('simulated interruption')
        return original(self,*args,**kwargs,_fault=fault)
    monkeypatch.setattr(PersistentEvidenceStore,'apply_analysis',wrapped)
    with pytest.raises(RuntimeError):request(w,cid,'contradiction',disagreement())
    assert w.view(cid)==before


def test_stale_and_concurrent_submissions_do_not_duplicate_or_choose_winner(case):
    w,cid=case;before=w.view(cid)
    def save(i):
        try:return request(w,cid,'contradiction',disagreement(),request_id='parallel-'+str(i),expected_revision=before['revision'],expected_ledger_revision=before['ledger_revision'])
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,range(2)))
    assert sum(r is not None for r in results)==1
    after=w.view(cid);assert len(after['state']['contradictions'])==1 and after['revision']==before['revision']+1
    assert after['state']['claims']==before['state']['claims']
    with pytest.raises(RuntimeError):request(w,cid,'contradiction',disagreement(),expected_revision=before['revision'])
    assert w.view(cid)==after


def test_analysis_authorization_is_required(case,monkeypatch):
    from dd_research_runtime import local_app
    w,cid=case;before=w.view(cid);monkeypatch.setattr(local_app,'_authorize',lambda actor,capability:False)
    with pytest.raises(PermissionError):request(w,cid,'contradiction',disagreement())
    assert w.view(cid)==before


def test_existing_identifier_cannot_overwrite_record(case):
    w,cid=case;request(w,cid,'contradiction',disagreement(),request_id='first-save');before=w.view(cid)
    with pytest.raises((ValueError,RuntimeError)):request(w,cid,'contradiction',disagreement(issue='Attempted replacement'),request_id='first-save')
    assert w.view(cid)==before


def test_disagreement_does_not_require_or_invent_evidence(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=create(w)
    for rid in ('first','second'):request(w,cid,'claim',dict(claim='Untested hypothesis '+rid,claim_type='causal',evidence_ids=[],rationale='Unresolved fixture'),request_id=rid)
    request(w,cid,'contradiction',disagreement(),request_id='no-evidence')
    v=w.view(cid);assert not v['state']['evidence'] and not v['state']['human_gates']
    assert all(c['evidence_origin']=='none' and c['disposition']=='unresolved' for c in v['state']['claims'].values())


def test_reports_retain_exact_disagreement_and_claim_versions_after_current_edits(tmp_path):
    w=Workspace(tmp_path/'workspace');cid=prepare_workspace(w);original=w.visit(cid,'V2');before=w.view(cid)
    request(w,cid,'claim',dict(claim='SYNTHETIC contrary interpretation',claim_type='descriptive',evidence_ids=['synthetic-synthetic-source'],rationale='Fixture only'),request_id='contrary')
    request(w,cid,'contradiction',disagreement(claim_a='claim-interpretation',claim_b='claim-contrary'),request_id='report-tension')
    v=w.view(cid);assert v['state']['workflow']==before['state']['workflow'] and v['state']['human_gates']==before['state']['human_gates']
    assert not any(r['current'] for r in v['reports'])
    request(w,cid,'report',dict(rationale='Retain disagreement without resolving it'),request_id='with-tension')
    report=copy.deepcopy(w.view(cid)['state']['outputs']['report-with-tension'])
    assert report['contradictions']['contradiction-report-tension']['disposition']=='unresolved'
    assert disagreement()['issue'].rstrip('.') in render_markdown(report)
    sr=w.view(cid)['revision'];w.store(cid).apply_analysis([dict(type='update_claim',claim_id='claim-contrary',patch=dict(claim='Later current interpretation text'))],operation_id='later-edit',actor=ACTOR,rationale='Fixture edit',expected_state_revision=sr,authorize=_authorize)
    final=w.view(cid);assert final['state']['outputs']['report-with-tension']==report
    old=next(c for c in report['claims'] if c['claim_id']=='claim-contrary')
    assert old['interpretation']['claim']=='SYNTHETIC contrary interpretation'
    assert old['evidence'][0]['evidence']['synthetic'] is True
    assert not any(r['current'] for r in final['reports'])
    historic=w.visit(cid,'V2');assert historic['visit']==original['visit'] and historic['context']==original['context']
