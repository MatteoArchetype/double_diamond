import io
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from dd_research_runtime import local_app
from dd_research_runtime.document_preview import preview_word_document
from test_local_app import create, request, source

PROPERTIES = b"""<cp:coreProperties
xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Urban heat methods</dc:title><dc:creator>Example author</dc:creator>
<dc:date>2025-06-01</dc:date><dc:source>https://example.org/report#methods</dc:source>
</cp:coreProperties>"""


WORD_BODY = b"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:t>Street </w:t><w:t>trees</w:t></w:r><w:hyperlink><w:r>
<w:t> provide shade</w:t></w:r></w:hyperlink><w:r><w:tab/><w:t>today</w:t></w:r></w:p>
<w:p/><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table text</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p><w:r><w:t>Third paragraph</w:t></w:r></w:p></w:body></w:document>"""


def word_bytes(properties, body=WORD_BODY):
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w') as document:
        document.writestr('[Content_Types].xml', '<Types/>')
        document.writestr('word/document.xml', body)
        if properties is not None:
            document.writestr('docProps/core.xml', properties)
    return buffer.getvalue()


def test_extracts_only_explicit_source_details():
    assert preview_word_document(word_bytes(PROPERTIES))['metadata'] == {
        'title': 'Urban heat methods', 'publisher': 'Example author',
        'date': '2025-06-01', 'url': 'https://example.org/report#methods',
    }
    assert not any(preview_word_document(word_bytes(None))['metadata'].values())
    assert not preview_word_document(word_bytes(PROPERTIES.replace(
        b'https://example.org/report#methods', b'javascript:alert(1)'
    )))['metadata']['url']


@pytest.mark.parametrize('data', [
    b'not a document', word_bytes(b'<!DOCTYPE anything>' + PROPERTIES),
    word_bytes(b'x' * 65537), word_bytes(b'<broken'),
], ids=['text', 'doctype', 'oversized', 'broken'])
def test_rejects_bad_or_oversized_properties(data):
    with pytest.raises(ValueError):
        preview_word_document(data)


@pytest.mark.parametrize('authorized', [True, False])
def test_preview_route_requires_token_and_does_not_need_workspace(authorized):
    data = word_bytes(PROPERTIES)
    origin = 'http://127.0.0.1:12345'
    headers = {'Host': '127.0.0.1:12345', 'Origin': origin,
               'Content-Type': 'application/octet-stream', 'Content-Length': str(len(data))}
    if authorized:
        headers['Authorization'] = 'Bearer private-token'
    replies = []
    handler = object.__new__(local_app.Handler)
    handler.server = SimpleNamespace(origin=origin, token='private-token')
    handler.path = '/api/document-preview'
    handler.headers = headers
    handler.rfile = io.BytesIO(data)
    handler._reply = lambda status, result: replies.append((status, result))
    handler.do_POST()
    assert replies[0][0] == (200 if authorized else 403)
    if authorized:
        assert replies[0][1]['metadata']['title'] == 'Urban heat methods'


def test_publication_date_retained_only_on_explicit_evidence_approval(tmp_path):
    workspace = local_app.Workspace(tmp_path)
    case = create(workspace)
    data = source(published_at='2025-06-01')
    with pytest.raises(PermissionError):
        request(workspace, case, 'source', dict(data, confirmed=False))
    assert not workspace.view(case)['state']['evidence']
    request(workspace, case, 'source', data, request_id='dated')
    assert workspace.view(case)['state']['evidence']['synthetic-dated']['metadata']['published_at'] == '2025-06-01'


def test_main_body_paragraphs_preserve_order_spacing_and_locators():
    result = preview_word_document(word_bytes(None))
    assert result['paragraphs'] == [
        {'number': 1, 'text': 'Street trees provide shade\ttoday'},
        {'number': 3, 'text': 'Third paragraph'},
    ]
    assert result['passage_notice'] == ''


@pytest.mark.parametrize('body', [b'<broken', b'x' * (1024 * 1024 + 1), b'<!DOCTYPE doc>' + WORD_BODY],
                         ids=['broken', 'oversized', 'doctype'])
def test_unavailable_body_preserves_metadata_preview(body):
    result = preview_word_document(word_bytes(PROPERTIES, body))
    assert result['metadata']['title'] == 'Urban heat methods'
    assert result['paragraphs'] == []
    assert result['passage_notice']
