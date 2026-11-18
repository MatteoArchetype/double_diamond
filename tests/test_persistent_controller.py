from dataclasses import replace
import sqlite3

import pytest
from test_persistent_ingestion import store, auth, batch, ingest
from dd_research_runtime.evidence_review import review_retrieval
from dd_research_runtime.persistent_controller import (
    run_persistent_controller_step, commit_controller_retrieval,
)
from dd_research_runtime.runtime import GateRequired


def output(sid='s1', synthetic=False):
    doc = batch(sid, synthetic)[0].documents[0]
    from dataclasses import asdict
    return {'status':'completed', 'documents':[asdict(doc)], 'summary':'candidate only'}


class Cycle:
    def __init__(self): self.events=[]
    def record(self, *event): self.events.append(event)


def prepare(store, *, action='retrieve', executor=None, decision=None, **options):
    return run_persistent_controller_step(store, Cycle(),
        step_fn=lambda state, cycle, **kw: decision or {'highest_value_action':action},
        step_context={}, executors={action:executor or (lambda **kw: output())}, **options)


def review(candidate, decision='approved'):
    snapshots = {doc.source_id:dict(text=doc.passage, location=doc.content_location)
                 for doc in candidate.validation.documents}
    return review_retrieval(candidate.validation, snapshots=snapshots, reviewer='human',
                            decision=decision, rationale='Independent snapshot checked')


def commit(store, candidate, r=None, **options):
    args = dict(operation_id='controller-s1', authorize=auth)
    args.update(options)
    return commit_controller_retrieval(store, candidate, r or review(candidate), **args)


def test_prepare_review_commit_restart(store):
    before = store.load()[0].snapshot()
    candidate = prepare(store)
    assert candidate.status == 'ready_for_review'
    assert candidate.state_revision == candidate.ledger_revision == 0
    assert store.load()[0].snapshot() == before
    assert store.ledger.revision() == 0
    result = commit(store, candidate)
    assert result['state_revision'] == result['ledger_revision'] == 1
    from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
    reopened = PersistentEvidenceStore(store.ledger.path)
    assert 's1' in reopened.load()[0].evidence
    assert commit(reopened, candidate) == result
    assert reopened.verify_integrity()['operations'] == 1


@pytest.mark.parametrize('decision', [
    {'highest_value_action':'retrieve', 'gate_required':True},
    {'highest_value_action':'request_human_input'},
    {'highest_value_action':'stop'},
])
def test_gates_and_stop_never_execute_or_ingest(store, decision):
    called=[]
    before = store.load()[0].snapshot()
    candidate = prepare(store, decision=decision, executor=lambda **kw: called.append(True))
    assert candidate.status in {'paused_for_human','stopped'}
    assert candidate.validation is None and not called
    with pytest.raises(PermissionError): commit_controller_retrieval(store,candidate,None,operation_id='blocked',authorize=auth)
    assert store.load()[0].snapshot() == before and store.ledger.revision() == 0


@pytest.mark.parametrize('status', ['failed','needs_human_review','no_result'])
def test_unsuccessful_retrieval_cannot_be_committed(store, status):
    candidate = prepare(store, executor=lambda **kw: {**output(), 'status':status})
    assert candidate.validation is None
    with pytest.raises(PermissionError): commit_controller_retrieval(store,candidate,None,operation_id='blocked',authorize=auth)
    assert store.load()[1] == 0


@pytest.mark.parametrize('action', ['search','compare','audit','test','reframe','synthesise'])
def test_other_action_output_is_never_evidence(store, action):
    candidate = prepare(store, action=action)
    assert candidate.status == 'completed' and candidate.validation is None
    with pytest.raises(PermissionError): commit_controller_retrieval(store,candidate,None,operation_id='blocked',authorize=auth)
    assert not store.load()[0].evidence


@pytest.mark.parametrize('raw', [
    {'status':'completed'}, {'status':'completed','documents':[]},
    {'status':'completed','documents':[{'source_id':'incomplete'}]},
])
def test_invalid_documents_fail_closed(store, raw):
    candidate = prepare(store, executor=lambda **kw: raw)
    assert candidate.status == 'rejected'
    with pytest.raises(PermissionError): commit_controller_retrieval(store,candidate,None,operation_id='blocked',authorize=auth)
    assert store.ledger.revision() == 0


def test_executor_exception_has_no_durable_effect(store):
    def fail(**kwargs): raise RuntimeError('executor failed')
    with pytest.raises(RuntimeError,match='executor failed'): prepare(store,executor=fail)
    assert store.load()[1] == store.ledger.revision() == 0


def test_callback_state_mutations_are_detached(store):
    def malicious_step(state, cycle, **kw):
        state.approve_gate('publication')
        state.evidence['unreviewed'] = {'synthetic':True}
        return {'highest_value_action':'retrieve'}
    candidate = run_persistent_controller_step(store,Cycle(),step_fn=malicious_step,
        step_context={},executors={'retrieve':lambda **kw:output()})
    commit(store,candidate)
    state, _ = store.load()
    assert 'unreviewed' not in state.evidence
    assert state.human_gates['publication']['status'] == 'pending_review'
    with pytest.raises(GateRequired): state.execute_gated('publication','publication')


def test_candidate_frozen_from_executor_owned_data(store):
    raw = output()
    candidate = prepare(store,executor=lambda **kw:raw)
    raw['documents'][0]['passage'] = 'changed after return'
    assert candidate.validation.documents[0].passage == 'Exact passage s1'
    commit(store,candidate)


def test_candidate_and_execution_mismatch_rejected(store):
    candidate = prepare(store)
    r = review(candidate)
    candidate.step.execution.output['documents'][0]['passage'] = 'changed'
    with pytest.raises(ValueError,match='does not match'): commit(store,candidate,r)
    assert store.load()[1] == 0


@pytest.mark.parametrize('kind', ['missing_auth','rejected_review','changed_review'])
def test_human_review_remains_required(store,kind):
    candidate = prepare(store)
    r, options = review(candidate), {}
    if kind == 'missing_auth': options['authorize'] = None
    elif kind == 'rejected_review': r = review(candidate, decision='rejected')
    else: r = replace(r,rationale='modified')
    with pytest.raises((PermissionError,ValueError)): commit(store,candidate,r,**options)
    assert store.load()[1] == store.ledger.revision() == 0


def test_review_source_snapshot_mismatch(store):
    candidate = prepare(store)
    with pytest.raises(ValueError,match='not verified'):
        review_retrieval(candidate.validation,snapshots={'s1':{'text':'unrelated','location':'p1'}},
                         reviewer='human',decision='approved',rationale='check')
    assert store.load()[1] == 0


def test_concurrent_ingestion_invalidates_candidate(store):
    candidate = prepare(store)
    ingest(store,'other')
    with pytest.raises(RuntimeError,match='stale state'): commit(store,candidate)
    assert 's1' not in store.load()[0].evidence and store.ledger.revision() == 1


def test_review_only_receipt_invalidates_candidate_ledger_revision(store):
    candidate = prepare(store)
    store.ledger.append(batch('other')[1],expected_revision=0)
    with pytest.raises(RuntimeError,match='stale ledger'): commit(store,candidate)
    assert store.load()[1] == 0 and not store.load()[0].evidence


def test_synthetic_and_review_only_revisions(store):
    store.ledger.append(batch('other')[1],expected_revision=0)
    candidate = prepare(store,executor=lambda **kw:output(synthetic=True))
    assert candidate.state_revision == 0 and candidate.ledger_revision == 1
    commit(store,candidate)
    state, sr, lr = store.load_with_revisions()
    assert (sr,lr) == (1,2)
    assert state.evidence['s1']['synthetic'] is True and 's1' not in state.sources


def test_corruption_blocks_callbacks(store):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db: db.execute('DELETE FROM ingestion_operations')
    called=[]
    with pytest.raises(ValueError,match='integrity'):
        run_persistent_controller_step(store,Cycle(),step_fn=lambda *a,**kw:called.append(True),
                                      step_context={},executors={})
    assert not called


def test_external_execution_not_repeated_on_commit_retry(store):
    called=[]
    candidate = prepare(store,executor=lambda **kw:called.append(True) or output())
    first = commit(store,candidate)
    assert commit(store,candidate) == first and len(called) == 1


def test_revision_snapshot_consistency(store,monkeypatch):
    from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore
    with sqlite3.connect(store.ledger.path) as db: db.execute('PRAGMA journal_mode=WAL')
    original = store._load
    def commit_during_read(db):
        ingest(PersistentEvidenceStore(store.ledger.path),'other')
        return original(db)
    monkeypatch.setattr(store,'_load',commit_during_read)
    candidate = prepare(store)
    assert (candidate.state_revision,candidate.ledger_revision) == (0,0)
    monkeypatch.setattr(store,'_load',original)
    with pytest.raises(RuntimeError,match='stale state'): commit(store,candidate)
