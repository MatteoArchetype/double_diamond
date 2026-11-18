import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from dd_research_runtime.file_preview import preview_file
from dd_research_runtime.local_app import Workspace
from test_local_app import create, request

TRANSCRIPT = b'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nExample recorded words.\n\n00:00:04.000 --> 00:00:05.000\nMore context.\n'


def pdf_bytes():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 100 Td (Example PDF evidence.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.parametrize(('name', 'data', 'location'), [
    ('report.pdf', None, 'Page 1'),
    ('notes.txt', b'First line\nExample evidence.', 'Line 1'),
    ('notes.md', b'# Interview\nExample evidence.', 'Line 1'),
    ('record.vtt', TRANSCRIPT, '00:00:01.000–00:00:03.000'),
    ('record.srt', b'1\n00:00:01,000 --> 00:00:03,000\nExample words.\n', '00:00:01,000–00:00:03,000'),
])
def test_formats_reopen_search_and_retain_locators(tmp_path, name, data, location):
    workspace = Workspace(tmp_path)
    cid = create(workspace)
    before = workspace.view(cid)
    lib = workspace.documents(cid)
    data = pdf_bytes() if data is None else data
    saved = lib.save(name, data)
    reopened = Workspace(tmp_path).documents(cid)
    assert reopened.original(saved['id']) == (name, data)
    assert reopened.context(saved['id'], 1)['location'] == location
    assert reopened.search('Example')['total'] >= 1
    assert workspace.view(cid) == before


def test_recording_transcript_concurrency_integrity_and_review(tmp_path):
    workspace = Workspace(tmp_path)
    cid = create(workspace)
    lib = workspace.documents(cid)
    saved = lib.save('interview.wav', b'RIFF'+b'\0'*4+b'WAVE'+b'\0'*8)
    assert saved['media'] and not saved['paragraphs']
    with ThreadPoolExecutor(max_workers=4) as pool:
        attached = list(pool.map(lambda _: lib.attach_transcript(saved['id'], 'interview.vtt', TRANSCRIPT), range(4)))
    assert len({item['transcript_sha256'] for item in attached}) == 1
    assert lib.search('recorded')['total'] == 1
    data = dict(document_id=saved['id'], paragraph=1, passage='Example recorded words.',
                title='Interview', publisher='Research team', group='interview',
                confirmed=False, synthetic=True, rationale='Checked fixture recording.')
    with pytest.raises(PermissionError):
        request(workspace, cid, 'document_source', data)
    request(workspace, cid, 'document_source', dict(data, confirmed=True), request_id='media-review')
    evidence = workspace.view(cid)['state']['evidence']['synthetic-media-review']
    assert evidence['synthetic'] is True
    assert '00:00:01.000' in evidence['exact_location']
    assert evidence['metadata']['transcript_sha256'] == attached[0]['transcript_sha256']
    with pytest.raises(ValueError, match='already has'):
        lib.attach_transcript(saved['id'], 'changed.vtt', TRANSCRIPT.replace(b'Example', b'Different'))
    with sqlite3.connect(lib.path) as db:
        db.execute("UPDATE transcripts SET data = ?", (b'changed',))
    with pytest.raises(ValueError, match='integrity'):
        lib.preview(saved['id'])


@pytest.mark.parametrize(('name','data'), [
    ('bad.pdf', b'bad'), ('bad.mp4', b'bad'), ('bad.vtt', b'plain prose'),
    ('bad.txt', b'\xff'), ('bad.txt', b'\0binary'), ('bad.exe', b'bad'),
])
def test_invalid_formats_are_rejected(name, data):
    with pytest.raises(ValueError):
        preview_file(name, data)


def test_upload_routes_and_original_download_preserve_format(tmp_path):
    from types import SimpleNamespace
    from dd_research_runtime.local_app import Handler
    workspace = Workspace(tmp_path)
    cid = create(workspace)
    origin = 'http://127.0.0.1:12345'

    def post(path, data):
        replies = []
        handler = object.__new__(Handler)
        handler.server = SimpleNamespace(origin=origin, token='private-token', workspace=workspace)
        handler.path = path
        handler.headers = {'Host': '127.0.0.1:12345', 'Origin': origin,
                           'Authorization': 'Bearer private-token',
                           'Content-Type': 'application/octet-stream', 'Content-Length': str(len(data))}
        handler.rfile = io.BytesIO(data)
        handler._reply = lambda status, result: replies.append((status, result))
        handler.do_POST()
        assert replies[0][0] == 200, replies
        return replies[0][1]

    preview = post('/api/document-preview?filename=report.pdf', pdf_bytes())
    assert preview['paragraphs'][0]['location'] == 'Page 1'
    saved = post('/api/documents?case='+cid+'&filename=interview.mp3', b'ID3'+b'\0'*20)
    attached = post('/api/document-transcript?case='+cid+'&document='+saved['id']+'&filename=interview.vtt', TRANSCRIPT)
    assert attached['paragraphs'][0]['text'] == 'Example recorded words.'
    assert not workspace.view(cid)['state']['evidence']


@pytest.mark.parametrize('stamp', [
    b'00:00:04.000 --> 00:00:03.000', b'00:99:01.000 --> 00:99:03.000'
])
def test_invalid_transcript_times(stamp):
    with pytest.raises(ValueError):
        preview_file('bad.vtt', TRANSCRIPT.replace(b'00:00:01.000 --> 00:00:03.000', stamp))
