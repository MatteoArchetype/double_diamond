"""Request-level contract tests for the local interface.

The other UI tests call Workspace methods directly; these open a real socket so
routing, headers, content types and error mapping cannot regress unnoticed.
"""
import http.client
import json
import threading
import uuid
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from dd_research_runtime.local_app import LocalServer, Workspace
from dd_research_runtime.source_draft import DRAFT_FIELDS


@pytest.fixture
def server(tmp_path):
    workspace = Workspace(tmp_path / 'workspace')
    instance = LocalServer(workspace, 0)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def _call(server, method, path, body=None, *, token=True, origin=True, headers=None, content_type=None):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
    sent = dict(headers or {})
    if token:
        sent['Authorization'] = 'Bearer ' + server.token
    if origin:
        sent['Origin'] = server.origin
    payload = None
    if body is not None:
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        sent['Content-Type'] = content_type or 'application/json'
    try:
        connection.request(method, path, body=payload, headers=sent)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def _create(server):
    status, _, raw = _call(server, 'POST', '/api/cases', dict(
        title='Contract case', question='What is verified?', scope='Tests only',
        max_visits=8, max_alternatives=3))
    assert status == 201, raw
    return json.loads(raw)['case_id']


def test_static_assets_are_public_but_never_carry_the_token(server):
    status, headers, body = _call(server, 'GET', '/', token=False, origin=False)
    assert status == 200
    assert b'Double Diamond' in body
    assert server.token.encode() not in body
    assert headers['Content-Security-Policy'].startswith("default-src 'self'")
    assert headers['Cache-Control'] == 'no-store'
    assert headers['X-Content-Type-Options'] == 'nosniff'


@pytest.mark.parametrize('token,origin,expected', [(False, False, 403), (False, True, 403), (True, False, 200)])
def test_reads_need_the_launch_token_but_not_an_origin(server, token, origin, expected):
    """Reads from a pasted link carry no Origin; writes do, and that is enforced below."""
    status, _, _ = _call(server, 'GET', '/api/cases', token=token, origin=origin)
    assert status == expected


def test_diagnostics_cli_prints_json_and_exits(tmp_path):
    result = subprocess.run(
        [sys.executable, '-m', 'dd_research_runtime.local_app',
         '--diagnostics', '--workspace', str(tmp_path / 'workspace')],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report['status'] == 'healthy'
    assert report['cases']['saved'] == 0
    assert str(tmp_path) not in result.stdout


def test_diagnostics_are_read_only_and_do_not_disclose_the_workspace_path(server):
    cid = _create(server)
    status, _, raw = _call(server, 'GET', '/api/diagnostics')
    assert status == 200
    result = json.loads(raw)
    assert result['status'] == 'healthy'
    assert result['cases']['saved'] == 1
    assert result['cases']['unavailable'] == 0
    assert result['workspace']['writable'] is True
    assert result['workspace']['total_bytes'] > 0
    assert 'workspace_path' not in result
    assert str(server.workspace.path) not in raw.decode()
    assert cid not in raw.decode()


def test_foreign_host_header_is_refused(server):
    status, _, raw = _call(server, 'GET', '/api/cases', headers={'Host': 'evil.example'})
    assert status == 403 and b'Unrecognized local host' in raw


def test_writes_reject_a_foreign_origin(server):
    status, _, raw = _call(server, 'POST', '/api/cases', {'title': 'x'}, origin=False)
    assert status == 403, raw


def test_unknown_paths_and_traversal_are_not_served(server):
    assert _call(server, 'GET', '/nope')[0] == 404
    assert _call(server, 'GET', '/../local_app.py')[0] == 404
    status, _, raw = _call(server, 'GET', '/api/document-original?case=' + '0' * 32 + '&document=../../etc/passwd')
    assert status == 400 and b'unknown case' in raw


def test_malformed_json_reports_a_readable_message(server):
    status, _, raw = _call(server, 'POST', '/api/cases', b'{not json', content_type='application/json')
    assert status == 400
    message = json.loads(raw)['error']
    assert 'could not be read' in message
    assert 'Expecting value' not in message and 'Traceback' not in message


def test_empty_upload_is_reported_as_empty_not_oversized(server):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/documents?case=' + cid + '&filename=note.txt', b'',
                           content_type='application/octet-stream')
    assert status == 400
    message = json.loads(raw)['error']
    assert 'empty' in message.lower() and '64 MiB' not in message


def test_checkpoint_download_and_report_have_the_right_content_types(server):
    cid = _create(server)
    status, headers, body = _call(server, 'GET', '/api/checkpoint?case=' + cid + '&revision=1')
    assert status == 200 and body[:2] == b'PK'
    assert headers['Content-Type'] == 'application/zip'
    assert 'attachment' in headers['Content-Disposition']


def test_stale_revision_is_rejected_without_touching_state(server):
    cid = _create(server)
    body = dict(case_id=cid, request=dict(action='report', data=dict(rationale='probe'),
                                          expected_revision=99, expected_ledger_revision=0,
                                          request_id=uuid.uuid4().hex))
    status, _, raw = _call(server, 'POST', '/api/action', body)
    assert status == 409 and b'changed' in raw
    state = json.loads(_call(server, 'GET', '/api/state?case=' + cid)[2])
    assert state['revision'] == 1 and not state['state']['outputs']


def test_rename_changes_only_the_title(server):
    cid = _create(server)
    before = json.loads(_call(server, 'GET', '/api/state?case=' + cid)[2])
    status, _, raw = _call(server, 'POST', '/api/case/rename', dict(case_id=cid, title='Renamed case'))
    assert status == 200, raw
    after = json.loads(_call(server, 'GET', '/api/state?case=' + cid)[2])
    assert after['meta']['title'] == 'Renamed case'
    assert after['revision'] == before['revision']
    assert after['state']['workflow'] == before['state']['workflow']


@pytest.mark.parametrize('title', ['', '   ', 'x' * 201])
def test_rename_rejects_blank_or_overlong_titles(server, title):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/case/rename', dict(case_id=cid, title=title))
    assert status == 400, raw


def test_delete_requires_the_exact_title_and_moves_the_case_to_trash(server):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/case/delete', dict(case_id=cid, title='wrong'))
    assert status == 400 and b'exact case title' in raw
    assert [case['case_id'] for case in json.loads(_call(server, 'GET', '/api/cases')[2])] == [cid]

    status, _, raw = _call(server, 'POST', '/api/case/delete', dict(case_id=cid, title='Contract case'))
    assert status == 200, raw
    assert json.loads(_call(server, 'GET', '/api/cases')[2]) == []
    trashed = list((server.workspace.path / '.trash').iterdir())
    assert len(trashed) == 1 and trashed[0].name.startswith(cid)
    assert (trashed[0] / 'research.sqlite').is_file()


def test_trashed_case_is_listed_and_restored_to_the_original_identifier(server):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/case/delete',
                           dict(case_id=cid, title='Contract case'))
    assert status == 200

    status, _, raw = _call(server, 'GET', '/api/trash')
    assert status == 200
    trash = json.loads(raw)['cases']
    assert len(trash) == 1
    assert trash[0]['case_id'] == cid
    assert trash[0]['title'] == 'Contract case'

    status, _, raw = _call(server, 'POST', '/api/case/restore',
                           dict(trash_id=trash[0]['trash_id']))
    assert status == 200
    restored = json.loads(raw)
    assert restored['case_id'] == cid
    assert json.loads(_call(server, 'GET', '/api/cases')[2])[0]['case_id'] == cid
    assert json.loads(_call(server, 'GET', '/api/trash')[2])['cases'] == []


def test_concurrent_trash_restore_requests_restore_only_once(server):
    cid = _create(server)
    before = server.workspace.view(cid)
    status, _, raw = _call(server, 'POST', '/api/case/delete',
                           dict(case_id=cid, title='Contract case'))
    assert status == 200, raw
    trash = json.loads(_call(server, 'GET', '/api/trash')[2])['cases']
    trash_id = trash[0]['trash_id']
    barrier = threading.Barrier(2)

    def restore():
        barrier.wait(timeout=5)
        return _call(server, 'POST', '/api/case/restore', dict(trash_id=trash_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: restore(), range(2)))

    assert sorted(status for status, _, _ in responses) == [200, 400]
    assert server.workspace.view(cid) == before
    assert json.loads(_call(server, 'GET', '/api/cases')[2])[0]['case_id'] == cid
    assert json.loads(_call(server, 'GET', '/api/trash')[2])['cases'] == []
    assert not (server.workspace.path / '.trash' / trash_id).exists()


def test_trash_listing_tolerates_case_restored_during_verification(server, monkeypatch):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/case/delete',
                           dict(case_id=cid, title='Contract case'))
    assert status == 200, raw
    trash_id = json.loads(_call(server, 'GET', '/api/trash')[2])['cases'][0]['trash_id']

    original_verify = server.workspace._verified_trash_case
    listing_started = threading.Event()
    resume_listing = threading.Event()
    verification_lock = threading.Lock()
    should_pause = True

    def pause_first_verification(folder):
        nonlocal should_pause
        with verification_lock:
            pause = should_pause
            should_pause = False
        if pause:
            listing_started.set()
            assert resume_listing.wait(timeout=5)
        return original_verify(folder)

    monkeypatch.setattr(server.workspace, '_verified_trash_case', pause_first_verification)
    with ThreadPoolExecutor(max_workers=1) as pool:
        listing = pool.submit(_call, server, 'GET', '/api/trash')
        try:
            assert listing_started.wait(timeout=5)
            status, _, raw = _call(server, 'POST', '/api/case/restore',
                                   dict(trash_id=trash_id))
            assert status == 200, raw
        finally:
            resume_listing.set()
        status, _, raw = listing.result(timeout=10)

    assert status == 200, raw
    assert json.loads(raw)['cases'] == []
    assert server.workspace.view(cid)['meta']['title'] == 'Contract case'


def test_trash_restore_refuses_to_overwrite_an_active_case(server, monkeypatch):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/case/delete',
                           dict(case_id=cid, title='Contract case'))
    assert status == 200, raw
    trash = json.loads(_call(server, 'GET', '/api/trash')[2])['cases']
    trash_id = trash[0]['trash_id']
    trash_folder = server.workspace.path / '.trash' / trash_id
    trashed_files = {item.name: item.read_bytes() for item in trash_folder.iterdir()}

    monkeypatch.setattr('dd_research_runtime.local_app._id', lambda: cid)
    status, _, raw = _call(server, 'POST', '/api/cases', dict(
        title='Replacement case',
        question='What is the replacement?',
        scope='Collision test only',
        max_visits=8,
        max_alternatives=3,
    ))
    assert status == 201, raw
    active_before = server.workspace.view(cid)

    status, _, raw = _call(server, 'POST', '/api/case/restore',
                           dict(trash_id=trash_id))
    assert status == 400
    assert b'original identifier' in raw
    assert server.workspace.view(cid) == active_before
    assert {item.name: item.read_bytes() for item in trash_folder.iterdir()} == trashed_files
    assert json.loads(_call(server, 'GET', '/api/trash')[2])['cases'] == trash


def test_trashed_case_survives_workspace_restart_and_restores_history(server):
    cid = _create(server)
    library = server.workspace.documents(cid)
    document = library.save('interview.wav', b'RIFF' + b'\0' * 4 + b'WAVE' + b'\0' * 8)
    library.attach_transcript(
        document['id'],
        'interview.vtt',
        b'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nA local transcript passage.\n',
    )
    draft = dict.fromkeys(DRAFT_FIELDS, '') | {
        'title': 'Unfinished source',
        'passage': 'Unfinished excerpt',
        'synthetic': True,
    }
    saved_draft = server.workspace.source_draft(cid).write(0, draft)
    lead = dict(
        url='https://example.org/candidate',
        title='Unreviewed source lead',
        publisher='Publisher',
    )
    server.workspace.shortlist(cid).change('keep', lead)

    before = server.workspace.view(cid)
    assert before['storage']['local_library_bytes'] > 0
    assert before['storage']['drafts_bytes'] > 0
    assert before['storage']['shortlist_bytes'] > 0
    server.workspace.action(cid, dict(
        action='claim',
        data=dict(
            claim='A saved interpretation survives recovery.',
            claim_type='descriptive',
            evidence_ids=[],
            rationale='Synthetic fixture for trash recovery.',
        ),
        expected_revision=before['revision'],
        expected_ledger_revision=before['ledger_revision'],
        request_id='trash-restart-history',
    ))
    before = server.workspace.view(cid)

    status, _, raw = _call(server, 'POST', '/api/case/delete',
                           dict(case_id=cid, title='Contract case'))
    assert status == 200, raw
    server.shutdown()

    restarted = LocalServer(Workspace(server.workspace.path), 0)
    thread = threading.Thread(target=restarted.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, raw = _call(restarted, 'GET', '/api/trash')
        assert status == 200
        trash = json.loads(raw)['cases']
        assert len(trash) == 1
        assert trash[0]['case_id'] == cid
        assert trash[0]['title'] == 'Contract case'

        status, _, raw = _call(restarted, 'POST', '/api/case/restore',
                               dict(trash_id=trash[0]['trash_id']))
        assert status == 200, raw
        assert json.loads(raw) == dict(case_id=cid, title='Contract case')

        restored = restarted.workspace.view(cid)
        assert restored == before
        assert restored['state']['claims']['claim-trash-restart-history']['claim'] == (
            'A saved interpretation survives recovery.'
        )
        restored_library = restarted.workspace.documents(cid)
        assert restored_library.list() == [
            dict(id=document['id'], filename='interview.wav')
        ]
        assert restored_library.search('local transcript passage')['total'] == 1
        assert restarted.workspace.source_draft(cid).read() == saved_draft
        assert restarted.workspace.shortlist(cid).read() == [lead]
        assert json.loads(_call(restarted, 'GET', '/api/trash')[2])['cases'] == []
    finally:
        restarted.shutdown()
        restarted.server_close()
        thread.join(timeout=5)


def test_restore_rejects_unknown_or_forged_trash_ids(server):
    status, _, raw = _call(server, 'POST', '/api/case/restore',
                           dict(trash_id='../anything'))
    assert status == 400
    assert b'Trash' in raw or b'trash' in raw


def test_corrupt_trashed_case_cannot_be_restored_through_the_api(server):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/case/delete',
                           dict(case_id=cid, title='Contract case'))
    assert status == 200, raw
    trash = json.loads(_call(server, 'GET', '/api/trash')[2])['cases']
    trash_folder = server.workspace.path / '.trash' / trash[0]['trash_id']
    database = trash_folder / 'research.sqlite'
    database.write_bytes(b'not a valid research database')
    trashed_files = {item.name: item.read_bytes() for item in trash_folder.iterdir()}

    status, _, raw = _call(server, 'GET', '/api/trash')
    assert status == 200
    unavailable = json.loads(raw)['cases']
    assert len(unavailable) == 1
    assert unavailable[0]['status'] == 'unavailable'

    status, _, raw = _call(server, 'POST', '/api/case/restore',
                           dict(trash_id=trash[0]['trash_id']))
    assert status == 400
    assert b'could not be verified' in raw
    assert not (server.workspace.path / cid).exists()
    assert {item.name: item.read_bytes() for item in trash_folder.iterdir()} == trashed_files
    assert json.loads(_call(server, 'GET', '/api/trash')[2])['cases'] == unavailable


def test_trashed_case_with_invalid_metadata_cannot_be_restored(server):
    cid = _create(server)
    status, _, raw = _call(server, 'POST', '/api/case/delete',
                           dict(case_id=cid, title='Contract case'))
    assert status == 200, raw
    trash = json.loads(_call(server, 'GET', '/api/trash')[2])['cases']
    trash_folder = server.workspace.path / '.trash' / trash[0]['trash_id']
    (trash_folder / 'case-info.json').write_text('{')
    trashed_files = {item.name: item.read_bytes() for item in trash_folder.iterdir()}

    unavailable = json.loads(_call(server, 'GET', '/api/trash')[2])['cases']
    assert len(unavailable) == 1
    assert unavailable[0]['status'] == 'unavailable'

    status, _, raw = _call(server, 'POST', '/api/case/restore',
                           dict(trash_id=trash[0]['trash_id']))
    assert status == 400
    assert b'could not be verified' in raw
    assert not (server.workspace.path / cid).exists()
    assert {item.name: item.read_bytes() for item in trash_folder.iterdir()} == trashed_files
    assert json.loads(_call(server, 'GET', '/api/trash')[2])['cases'] == unavailable


def test_catalog_is_ordered_by_recent_activity(server):
    first = _create(server)
    second = _create(server)
    _, _, raw = _call(server, 'POST', '/api/case/rename', dict(case_id=second, title='Touched last'))
    cases = json.loads(_call(server, 'GET', '/api/cases')[2])
    assert [case['case_id'] for case in cases][0] == second
    assert all(isinstance(case['updated_at'], int) for case in cases)
    assert {first, second} == {case['case_id'] for case in cases}


def test_served_file_types_do_not_come_from_the_platform():
    """Windows has no mime database; every served name is mapped explicitly."""
    from dd_research_runtime import local_app
    assert local_app.content_type('report.docx').endswith('wordprocessingml.document')
    assert local_app.content_type('app.js').startswith('text/javascript')
    assert local_app.content_type('REPORT.PDF') == 'application/pdf'
    assert local_app.content_type('unknown.zzz') == 'application/octet-stream'
