"""Cross-record corruption and consistent-read regression coverage for Cycle 116."""
import json
import sqlite3
from pathlib import Path

import pytest
from test_persistent_ingestion import store, batch, ingest, auth
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore, _checksum, _encode
from dd_research_runtime.review_ledger import _hash
from dd_research_runtime.runtime import ResearchState


def edit_result(store, mutate, sid='s1'):
    with sqlite3.connect(store.ledger.path) as db:
        encoded = db.execute('SELECT result FROM ingestion_operations WHERE operation_id=?', (sid,)).fetchone()[0]
        result = json.loads(encoded)
        result = mutate(result) or result
        encoded = _encode(result)
        db.execute('UPDATE ingestion_operations SET result=?,result_digest=? WHERE operation_id=?', (encoded, _checksum(encoded), sid))


def edit_state(store, mutate):
    with sqlite3.connect(store.ledger.path) as db:
        state = json.loads(db.execute('SELECT snapshot FROM research_state').fetchone()[0])
        mutate(state)
        encoded = _encode(state)
        db.execute('UPDATE research_state SET snapshot=?,digest=?', (encoded, _checksum(encoded)))


def assert_closed(store):
    with sqlite3.connect(store.ledger.path) as db:
        before = db.iterdump()
        before = list(before)
    for action in (store.load, store.verify_integrity, lambda: ingest(store, 's2', expected_state_revision=1, expected_ledger_revision=1), lambda: ingest(store)):
        with pytest.raises(ValueError, match='integrity'): action()
    with sqlite3.connect(store.ledger.path) as db:
        assert list(db.iterdump()) == before


def test_empty_and_review_only_history(store):
    assert store.verify_integrity() == dict(state_revision=0, ledger_revision=0, operations=0)
    store.ledger.append(batch('review_only')[1], expected_revision=0)
    ingest(store, expected_ledger_revision=1)
    assert store.verify_integrity() == dict(state_revision=1, ledger_revision=2, operations=1)


def test_bootstrap_evidence_is_not_claimed_as_new_operation(tmp_path):
    initial = ResearchState()
    from dd_research_runtime.evidence_review import ingest_with_review
    ingest_with_review(initial, *batch('bootstrap'), authorize=auth)
    s = PersistentEvidenceStore(tmp_path/'bootstrap.db')
    s.initialize(initial)
    ingest(s)
    assert s.verify_integrity()['operations'] == 1
    assert len(s.load()[0].evidence) == 2


@pytest.mark.parametrize('damage', ['delete_operation', 'delete_receipt', 'request_digest', 'review_digest', 'revision'])
def test_partial_database_corruption(store, damage):
    ingest(store)
    sql = {
        'delete_operation': 'DELETE FROM ingestion_operations',
        'delete_receipt': 'DELETE FROM receipts',
        'request_digest': "UPDATE ingestion_operations SET request_digest='broken'",
        'review_digest': "UPDATE ingestion_operations SET review_digest='missing'",
        'revision': 'UPDATE research_state SET revision=9',
    }[damage]
    with sqlite3.connect(store.ledger.path) as db: db.execute(sql)
    assert_closed(store)


@pytest.mark.parametrize('field,value', [
    ('operation_id','other'), ('state_revision',True), ('state_revision',0),
    ('ledger_revision',True), ('ledger_revision',7), ('entry_hash','wrong'),
    ('evidence',[]), ('evidence',[{}]), ('evidence','text'),
])
def test_recomputed_result_checksum_does_not_hide_inconsistency(store, field, value):
    ingest(store)
    edit_result(store, lambda result: result.update({field:value}))
    assert_closed(store)


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(finding='rewritten'),
    lambda r: r.update(synthetic=True),
    lambda r: r.update(exact_location='p2'),
])
def test_changed_evidence_with_new_state_checksum(store, mutate):
    ingest(store)
    edit_state(store, lambda state: mutate(state['evidence']['s1']))
    assert_closed(store)


def test_missing_evidence_with_new_state_checksum(store):
    ingest(store)
    edit_state(store, lambda state: state['evidence'].clear())
    assert_closed(store)


@pytest.mark.parametrize('field,value', [('url','https://different.example'), ('provenance','changed'), ('independence_cluster','changed')])
def test_source_inconsistency_with_new_checksum(store, field, value):
    ingest(store)
    edit_state(store, lambda state: state['sources']['s1'].update({field:value}))
    assert_closed(store)


def test_duplicate_state_revision(store):
    ingest(store)
    ingest(store, 's2', expected_state_revision=1, expected_ledger_revision=1)
    edit_result(store, lambda result: result.update(state_revision=1), 's2')
    with pytest.raises(ValueError, match='integrity'): store.load()


def test_reversed_ledger_order(store):
    ingest(store)
    ingest(store, 's2', expected_state_revision=1, expected_ledger_revision=1)
    edit_result(store, lambda result: result.update(state_revision=2), 's1')
    edit_result(store, lambda result: result.update(state_revision=1), 's2')
    with pytest.raises(ValueError, match='ordering integrity'): store.verify_integrity()


def test_rejected_receipt_cannot_back_committed_evidence(store):
    ingest(store)
    with sqlite3.connect(store.ledger.path) as db:
        row = db.execute('SELECT review_digest,batch_digest,reviewer,rationale,previous_hash FROM receipts').fetchone()
        data = dict(zip(('review_digest','batch_digest','reviewer','rationale','previous_hash'), row), decision='rejected')
        digest = _hash(data)
        db.execute("UPDATE receipts SET decision='rejected',entry_hash=?", (digest,))
    edit_result(store, lambda result: result.update(entry_hash=digest))
    assert store.ledger.verify()  # Valid chain alone is insufficient.
    assert_closed(store)


@pytest.mark.parametrize('method', ['load', 'verify_integrity'])
def test_read_uses_consistent_snapshot_during_commit(store, monkeypatch, method):
    with sqlite3.connect(store.ledger.path) as db: db.execute('PRAGMA journal_mode=WAL')
    original = store._load
    def concurrent_commit(db):
        ingest(PersistentEvidenceStore(store.ledger.path))
        return original(db)
    monkeypatch.setattr(store, '_load', concurrent_commit)
    result = getattr(store, method)()
    if method == 'load': assert result[1] == 0 and not result[0].evidence
    else: assert result == dict(state_revision=0, ledger_revision=0, operations=0)
    monkeypatch.setattr(store, '_load', original)
    assert store.verify_integrity() == dict(state_revision=1, ledger_revision=1, operations=1)


def test_valid_synthetic_history(store):
    store.ingest(*batch(synthetic=True), operation_id='syn', expected_state_revision=0, expected_ledger_revision=0, authorize=auth)
    assert store.verify_integrity()['operations'] == 1
    assert store.load()[0].evidence['s1']['synthetic']


def test_cycle115_database_compatibility_without_reinitialization(tmp_path):
    path = tmp_path/'legacy.db'
    fixture = Path(__file__).parent/'fixtures'/'cycle115_ingested.sql'
    with sqlite3.connect(path) as db: db.executescript(fixture.read_text())
    store = PersistentEvidenceStore(path)
    assert store.verify_integrity() == dict(state_revision=1, ledger_revision=1, operations=1)
    assert ingest(store)['state_revision'] == 1  # Cycle 115 request remains retryable.
    ingest(store, 's2', expected_state_revision=1, expected_ledger_revision=1)
    assert store.verify_integrity() == dict(state_revision=2, ledger_revision=2, operations=2)


def test_huge_corrupt_revision_fails_without_allocating_revision_range(store):
    with sqlite3.connect(store.ledger.path) as db:
        db.execute('UPDATE research_state SET revision=9223372036854775807')
    with pytest.raises(ValueError, match='revision integrity'): store.load()
