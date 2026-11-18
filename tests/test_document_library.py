import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from dd_research_runtime.local_app import Workspace
from test_document_preview import PROPERTIES, WORD_BODY, word_bytes
from test_local_app import create


def test_document_survives_reopen_without_changing_evidence(tmp_path):
    workspace = Workspace(tmp_path)
    case, other = create(workspace), create(workspace)
    before = workspace.view(case)
    data = word_bytes(PROPERTIES)
    result = workspace.documents(case).save('research.docx', data)
    reopened = Workspace(tmp_path).documents(case)
    assert reopened.list() == [dict(id=result['id'], filename='research.docx')]
    assert reopened.preview(result['id']) == result
    assert reopened.preview(result['id'])['paragraphs']
    assert workspace.documents(other).list() == []
    with pytest.raises(ValueError, match='not found'):
        workspace.documents(other).preview(result['id'])
    assert workspace.view(case) == before


def test_concurrent_duplicate_uploads_keep_one_original(tmp_path):
    workspace = Workspace(tmp_path)
    case = create(workspace)
    data = word_bytes(PROPERTIES)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda n: workspace.documents(case).save(f'copy-{n}.docx', data), range(8)
        ))
    assert len({(r['id'], r['filename']) for r in results}) == 1
    assert len(workspace.documents(case).list()) == 1


def test_invalid_file_and_corruption_are_detected(tmp_path):
    workspace = Workspace(tmp_path)
    library = workspace.documents(create(workspace))
    with pytest.raises(ValueError):
        library.save('../research.docx', word_bytes(PROPERTIES))
    with pytest.raises(ValueError):
        library.save('research.docx', b'broken')
    assert library.list() == []
    result = library.save('research.docx', word_bytes(PROPERTIES))
    with sqlite3.connect(library.path) as db:
        db.execute('UPDATE documents SET data = ?', (b'changed',))
    with pytest.raises(ValueError, match='integrity'):
        library.preview(result['id'])


def test_search_finds_case_local_paragraphs_with_source_details(tmp_path):
    workspace = Workspace(tmp_path)
    case, other = create(workspace), create(workspace)
    before = workspace.view(case)
    library = workspace.documents(case)
    first = library.save('streets.docx', word_bytes(PROPERTIES))
    library.save('parks.docx', word_bytes(PROPERTIES, WORD_BODY.replace(b'Street ', b'Park ')))
    workspace.documents(other).save('private.docx', word_bytes(PROPERTIES))
    result = library.search('  TREES provide  ')
    assert result['total'] == 2
    assert [item['filename'] for item in result['matches']] == ['streets.docx', 'parks.docx']
    assert result['matches'][0]['id'] == first['id']
    assert result['matches'][0]['number'] == 1
    assert result['matches'][0]['metadata'] == first['metadata']
    assert result['incomplete'] == []
    assert workspace.view(case) == before


def test_search_caps_results_and_reports_unavailable_documents(tmp_path):
    workspace = Workspace(tmp_path)
    library = workspace.documents(create(workspace))
    good = library.save('matches.docx', word_bytes(PROPERTIES, WORD_BODY.replace(
        b'<w:p/>', b'<w:p><w:r><w:t>trees</w:t></w:r></w:p>' * 12
    )))
    broken = library.save('broken.docx', word_bytes(PROPERTIES, b'<invalid>'))
    assert broken['passage_notice']
    result = library.search('trees')
    assert result['total'] == 13 and len(result['matches']) == 10
    assert all(item['id'] == good['id'] for item in result['matches'])
    assert result['incomplete'] == ['broken.docx']
    with pytest.raises(ValueError):
        library.search('   ')


def test_keyword_search_ranks_coverage_then_phrase_and_preserves_exact_mode(tmp_path):
    workspace = Workspace(tmp_path)
    library = workspace.documents(create(workspace))
    body = WORD_BODY.replace(b'<w:p/>', b''.join(
        b'<w:p><w:r><w:t>' + text + b'</w:t></w:r></w:p>'
        for text in [b'trees'] * 11 + [b'Heat near trees', b'Trees heat', b'Trees heat again', b'Treetops']
    ))
    library.save('source.docx', word_bytes(PROPERTIES, body))
    ranked = library.search('  TREES heat  ', 'keywords')
    assert ranked['total'] == 15
    assert len(ranked['matches']) == 10
    assert [item['text'] for item in ranked['matches'][:3]] == ['Trees heat', 'Trees heat again', 'Heat near trees']
    assert ranked['matches'][2]['matched_keywords'] == ['trees', 'heat']
    assert ranked['matches'][3]['number'] == 1
    assert [item['text'] for item in library.search('trees heat')['matches']] == ['Trees heat', 'Trees heat again']
    assert library.search('tree', 'keywords')['total'] == 0
    assert library.search('trees, trees!', 'keywords')['matches'][0]['matched_keywords'] == ['trees']


@pytest.mark.parametrize(('query', 'mode'), [('trees', 'unknown'), ('...', 'keywords')])
def test_invalid_search_options_are_rejected(tmp_path, query, mode):
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError):
        workspace.documents(create(workspace)).search(query, mode)


def test_passage_context_preserves_numbers_and_is_case_local(tmp_path):
    workspace = Workspace(tmp_path)
    case, other = create(workspace), create(workspace)
    before = workspace.view(case)
    library = workspace.documents(case)
    saved = library.save('context.docx', word_bytes(PROPERTIES))
    result = library.context(saved['id'], 1)
    assert result['filename'] == 'context.docx'
    assert result['number'] == 1
    assert result['paragraphs'] == saved['paragraphs']
    with pytest.raises(ValueError, match='unavailable'):
        library.context(saved['id'], 2)
    with pytest.raises(ValueError, match='not found'):
        workspace.documents(other).context(saved['id'], 1)
    assert workspace.view(case) == before


def test_passage_context_is_bounded_and_checks_integrity(tmp_path):
    workspace = Workspace(tmp_path)
    library = workspace.documents(create(workspace))
    saved = library.save('context.docx', word_bytes(PROPERTIES, WORD_BODY.replace(
        b'<w:p/>', b'<w:p><w:r><w:t>Neighbor text</w:t></w:r></w:p>' * 10
    )))
    assert [p['number'] for p in library.context(saved['id'], 5)['paragraphs']] == [3, 4, 5, 6, 7]
    with pytest.raises(ValueError, match='valid paragraph'):
        library.context(saved['id'], 0)
    with sqlite3.connect(library.path) as db:
        db.execute('UPDATE documents SET data = ?', (b'changed',))
    with pytest.raises(ValueError, match='integrity'):
        library.context(saved['id'], 5)


def test_approve_local_paragraph_retains_provenance_and_context(tmp_path):
    from test_local_app import request
    workspace = Workspace(tmp_path)
    case, other = create(workspace), create(workspace)
    saved = workspace.documents(case).save('private.docx', word_bytes(PROPERTIES))
    data = dict(document_id=saved['id'], paragraph=1, passage=saved['paragraphs'][0]['text'],
                title='Original report', publisher='Research team', group='research-team',
                confirmed=True, synthetic=False, rationale='Checked the original document.')
    before = workspace.view(case)
    with pytest.raises(PermissionError):
        request(workspace, case, 'document_source', dict(data, confirmed=False))
    with pytest.raises(ValueError, match='does not match'):
        request(workspace, case, 'document_source', dict(data, passage='Altered text'))
    with pytest.raises(ValueError, match='not found'):
        request(workspace, other, 'document_source', data)
    assert workspace.view(case) == before
    request(workspace, case, 'document_source', data, request_id='file-review')
    view = workspace.view(case)
    assert view['ledger_revision'] == 1 and view['state']['workflow']['phase'] == 'discover'
    evidence = view['state']['evidence']['source-file-review']
    assert evidence['metadata']['document_sha256'] == saved['id']
    assert evidence['metadata']['url'] == 'urn:sha256:' + saved['id']
    assert evidence['synthetic'] is False
    assert evidence['exact_location'] == 'private.docx · Main-body paragraph 1'
    retained = workspace.source_context(case, 'source-file-review', view['revision'])
    assert retained['snapshot']['text'] == data['passage'] + '\n\nThird paragraph'
    with pytest.raises(ValueError, match='duplicate'):
        request(workspace, case, 'document_source', data)
    payload, _ = workspace.backup(case, view['revision'])
    assert workspace.inspect_backup(payload)


def test_synthetic_local_file_retains_synthetic_classification(tmp_path):
    from test_local_app import request
    workspace = Workspace(tmp_path)
    case = create(workspace)
    saved = workspace.documents(case).save('fixture.docx', word_bytes(PROPERTIES))
    request(workspace, case, 'document_source', dict(
        document_id=saved['id'], paragraph=1, passage=saved['paragraphs'][0]['text'],
        title='Fixture', publisher='Test', group='fixture', confirmed=True,
        synthetic=True, rationale='Synthetic practice example.'
    ), request_id='practice')
    evidence = workspace.view(case)['state']['evidence']['synthetic-practice']
    assert evidence['synthetic'] is True
    assert evidence['provenance'] == 'synthetic_local_document'


def test_original_download_returns_exact_case_local_bytes(tmp_path):
    from types import SimpleNamespace
    from urllib.parse import quote
    from dd_research_runtime.local_app import Handler

    workspace = Workspace(tmp_path)
    case, other = create(workspace), create(workspace)
    filename = 'Rapport 2026 – Ø.docx'
    data = word_bytes(PROPERTIES)
    saved = workspace.documents(case).save(filename, data)
    assert workspace.documents(case).original(saved['id']) == (filename, data)

    origin = 'http://127.0.0.1:12345'
    handler = object.__new__(Handler)
    handler.server = SimpleNamespace(origin=origin, token='private-token', workspace=workspace)
    handler.headers = {'Host': '127.0.0.1:12345', 'Authorization': 'Bearer private-token'}
    replies = []
    handler._reply = lambda *response: replies.append(response)
    handler.path = f"/api/document-original?case={case}&document={saved['id']}"
    handler.do_GET()
    status, payload, mime, headers = replies[-1]
    assert status == 200 and payload == data
    assert mime.endswith('wordprocessingml.document')
    assert headers['Content-Disposition'].endswith(quote(filename, safe=''))

    handler.path = f"/api/document-original?case={other}&document={saved['id']}"
    handler.do_GET()
    assert replies[-1][0] == 400
    del handler.headers['Authorization']
    handler.do_GET()
    assert replies[-1][0] == 403
