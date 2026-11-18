import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_persistent_ingestion import store, ingest
from test_analysis_transactions import apply, add_claim
from dd_research_runtime.gate_transactions import binding
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
from dd_research_runtime.checkpoints import create_checkpoint,restore_checkpoint


def auth(actor,permission):return actor=='human' and permission in {'gate_propose','gate_decide'}


def action():
    return dict(type='set_disposition',disposition_id='withdraw-1',claim_id='C1',disposition='withdraw',rationale='Fixture withdrawal',evidence_ids=['s1'],prior_status='draft',new_status='withdrawn',material_uncertainties=[],decision_relevance='Fixture only')


def setup(store):
    ingest(store);apply(store,[add_claim()])


def gate(store,command,oid,revision,**options):
    return store.apply_gate(command,operation_id=oid,actor='human',rationale='Simulated human decision',expected_state_revision=revision,authorize=auth,**options)


def propose(store,**options):return gate(store,dict(type='propose',gate_id='G1',action=action()),'proposal',2,**options)
def decide(store,decision='approve',**options):return gate(store,dict(type='decide',gate_id='G1',decision=decision,proposal_digest=binding(action())),'decision',3,**options)
def execute(store,**options):
    args=dict(operation_id='execute',expected_state_revision=4);args.update(options)
    return apply(store,[dict(action(),gate_id='G1')],**args)


def test_gate_roundtrip_single_use_checkpoint(store,tmp_path):
    setup(store);before=store.load()[0];propose(store);decide(store);result=execute(store)
    reopened=PersistentEvidenceStore(store.ledger.path);state,revision=reopened.load()
    assert revision==5 and state.claims['C1']['status']=='withdrawn'
    assert state.human_gates['G1']['status']=='executed'
    assert state.human_gates['G1']['decision_actor']=='human'
    assert state.claim_dispositions['withdraw-1']['decision_gate_id']=='G1'
    assert state.evidence==before.evidence and state.sources==before.sources
    assert reopened.ledger.revision()==1
    assert execute(reopened)==result
    assert decide(reopened)['state_revision']==4
    with pytest.raises((PermissionError,ValueError)):
        apply(reopened,[dict(action(),gate_id='G1')],operation_id='again',expected_state_revision=5)
    path=tmp_path/'checkpoint.zip';create_checkpoint(reopened,path);target=tmp_path/'restored.db';restore_checkpoint(path,target)
    assert PersistentEvidenceStore(target).load()[0].snapshot()==state.snapshot()


@pytest.mark.parametrize('decision',['reject','pending'])
def test_unapproved_gate_cannot_execute(store,decision):
    setup(store);propose(store)
    revision=3
    if decision=='reject':decide(store,'reject');revision=4
    with pytest.raises(PermissionError):execute(store,expected_state_revision=revision)
    assert store.load()[1]==revision


def test_authorization_digest_stale_and_legacy(store):
    setup(store)
    for callback in (None,lambda *args:1,lambda *args:False):
        with pytest.raises(PermissionError):store.apply_gate(dict(type='propose',gate_id='G1',action=action()),operation_id='proposal',actor='human',rationale='Fixture',expected_state_revision=2,authorize=callback)
    propose(store)
    with pytest.raises(PermissionError):gate(store,dict(type='decide',gate_id='G1',decision='approve',proposal_digest='wrong'),'wrong',3)
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=3)
    with pytest.raises(PermissionError):gate(store,dict(type='decide',gate_id='G1',decision='approve',proposal_digest=binding(action())),'decision',4)
    assert store.load()[1]==4


def test_exact_action_and_target_binding(store):
    setup(store);propose(store);decide(store)
    changed=dict(action(),rationale='Different',gate_id='G1')
    with pytest.raises(PermissionError):apply(store,[changed],operation_id='changed',expected_state_revision=4)
    apply(store,[dict(type='update_claim',claim_id='C1',patch=dict(confidence='low'))],operation_id='change',expected_state_revision=4)
    with pytest.raises(PermissionError):execute(store,expected_state_revision=5)
    assert store.load()[0].human_gates['G1']['status']=='approved'


@pytest.mark.parametrize('phase',['after_staging','after_state','after_journal','before_commit','after_commit'])
@pytest.mark.parametrize('stage',['propose','decide','execute'])
def test_atomic_failure_and_retry(store,phase,stage):
    setup(store)
    if stage in {'decide','execute'}:propose(store)
    if stage=='execute':decide(store)
    before=store.load()[1]
    def fault(name):
        if name==phase:raise RuntimeError('interrupted')
    operation={'propose':propose,'decide':decide,'execute':execute}[stage]
    with pytest.raises(RuntimeError,match='interrupted'):operation(store,_fault=fault)
    reopened=PersistentEvidenceStore(store.ledger.path)
    assert reopened.load()[1]==before+(phase=='after_commit')
    operation(reopened)
    assert reopened.load()[1]==before+1


def test_concurrent_decisions_one_winner(store):
    setup(store);propose(store)
    def write(index):
        try:return gate(store,dict(type='decide',gate_id='G1',decision='approve' if index==0 else 'reject',proposal_digest=binding(action())),'decision-'+str(index),3)
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,range(2)))
    assert sum(r is not None for r in results)==1
    assert store.load()[1]==4


def test_invalid_proposal_no_partial_gate(store):
    setup(store);bad=action();bad['disposition']='split'
    with pytest.raises(ValueError):gate(store,dict(type='propose',gate_id='G1',action=bad),'bad',2)
    assert 'G1' not in store.load()[0].human_gates


def crash_gate(path,phase,stage):
    import os
    def fault(name):
        if name==phase:os._exit(73)
    {'propose':propose,'decide':decide,'execute':execute}[stage](PersistentEvidenceStore(path),_fault=fault)


@pytest.mark.parametrize('phase',['after_state','after_journal','before_commit','after_commit'])
@pytest.mark.parametrize('stage',['propose','decide','execute'])
def test_process_death_recovery(store,phase,stage):
    import multiprocessing
    setup(store)
    if stage in {'decide','execute'}:propose(store)
    if stage=='execute':decide(store)
    before=store.load()[1]
    process=multiprocessing.get_context('spawn').Process(target=crash_gate,args=(store.ledger.path,phase,stage))
    process.start();process.join(15)
    if process.is_alive():process.terminate();process.join();pytest.fail('child timeout')
    assert process.exitcode==73
    reopened=PersistentEvidenceStore(store.ledger.path)
    assert reopened.load()[1]==before+(phase=='after_commit')
    {'propose':propose,'decide':decide,'execute':execute}[stage](reopened)
    assert reopened.load()[1]==before+1


@pytest.mark.parametrize('action_name',['publication','primary_research','sensitive_access','consequential_action','scope_change','material_reframing','phase_transition'])
def test_bounded_actions_exact_payload_and_rejection(store,action_name):
    callback=lambda actor,p:actor=='human' and p in {'gate_propose','gate_decide','gate_execute'}
    action=dict(type='gated_action',action=action_name,payload=dict(fixture_only=True,report_digest='fixture-digest'))
    def write(command,oid,revision):return store.apply_gate(command,operation_id=oid,actor='human',rationale='Fixture only',expected_state_revision=revision,authorize=callback)
    write(dict(type='propose',gate_id='G1',action=action),'p',0)
    with pytest.raises(PermissionError):write(dict(type='execute',gate_id='G1',action=action),'early',1)
    write(dict(type='decide',gate_id='G1',decision='approve',proposal_digest=binding(action)),'d',1)
    changed=copy.deepcopy(action);changed['payload']['report_digest']='different'
    with pytest.raises(PermissionError):write(dict(type='execute',gate_id='G1',action=changed),'wrong',2)
    write(dict(type='execute',gate_id='G1',action=action),'x',2)
    assert store.load()[0].human_gates['G1']['status']=='executed'
    assert store.ledger.revision()==0


def test_gate_audit_and_operation_collision(store):
    setup(store);propose(store)
    record=store.load_gate_operation('proposal')
    assert record['request']['actor']=='human' and len(record['entry_hash'])==64
    with pytest.raises(ValueError):apply(store,[add_claim('C3')],operation_id='proposal',expected_state_revision=3)
    with pytest.raises(KeyError):store.load_gate_operation('missing')
    with pytest.raises(ValueError):gate(store,dict(type='propose',gate_id='G2',action=action()),'analysis-1',3)


def test_failed_later_command_restores_consumed_approval(store):
    setup(store);propose(store);decide(store)
    with pytest.raises(ValueError):apply(store,[dict(action(),gate_id='G1'),dict(type='unsupported')],operation_id='bad-batch',expected_state_revision=4)
    state,revision=store.load()
    assert revision==4 and state.human_gates['G1']['status']=='approved' and state.claims['C1']['status']=='draft'
    execute(store)


def test_retries_require_current_permission(store):
    setup(store);propose(store)
    with pytest.raises(PermissionError):store.apply_gate(dict(type='propose',gate_id='G1',action=action()),operation_id='proposal',actor='human',rationale='Simulated human decision',expected_state_revision=2,authorize=lambda *args:False)
    assert store.load()[1]==3


def test_bootstrap_cannot_forge_durable_decision(tmp_path):
    from dd_research_runtime.runtime import ResearchState
    from dd_research_runtime.gate_transactions import target_digest
    state=ResearchState();state.add_claim(dict(claim_id='C1',claim='Fixture unresolved',claim_type='descriptive',disposition='unresolved',status='draft',evidence_ids=[]))
    command=action();command['evidence_ids']=[]
    state.human_gates['G1']=dict(gate_type='claim_disposition',status='approved',action=command,action_digest=binding(command),target_digest=target_digest(state,command),proposal_operation_id='forged-p',decision_operation_id='forged-d')
    saved=PersistentEvidenceStore(tmp_path/'forged.db');saved.initialize(state)
    with pytest.raises(ValueError,match='durable proposal/decision'):
        apply(saved,[dict(command,gate_id='G1')],operation_id='execute',expected_state_revision=0)
    assert saved.load()[1]==0
