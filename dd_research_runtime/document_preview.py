"""Preview bibliographic hints and main-body text without retaining the upload."""
import io
import re
import xml.etree.ElementTree as ET
import zlib
from zipfile import BadZipFile, ZipFile

from .payload_limits import MAX_PASSAGE_BYTES
from .source_shortlist import _canonical_url

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_PROPERTIES_BYTES = 64 * 1024
MAX_BODY_BYTES = 1024 * 1024
MAX_PARAGRAPHS = 2000
DC = '{http://purl.org/dc/elements/1.1/}'
CORE = '{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}'
WORD = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
XML_ERRORS = (BadZipFile, ET.ParseError, UnicodeError, RuntimeError, NotImplementedError, zlib.error)


def _read_xml(document, name, limit):
    entry = document.getinfo(name)
    if entry.file_size > limit:
        raise ValueError('This part of the document exceeds the preview size limit.')
    with document.open(entry) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('This part of the document exceeds the preview size limit.')
    text = data.decode('utf-8-sig')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I):
        raise ValueError('Unsupported XML in the Word document.')
    return ET.fromstring(text)


def _metadata(document):
    result = dict(title='', publisher='', date='', url='')
    if 'docProps/core.xml' not in document.namelist():
        return result
    root = _read_xml(document, 'docProps/core.xml', MAX_PROPERTIES_BYTES)
    if root.tag != CORE + 'coreProperties':
        raise ValueError('Unsupported Word document properties.')
    result['title'] = (root.findtext(DC + 'title') or '').strip()[:500]
    result['publisher'] = (root.findtext(DC + 'creator') or '').strip()[:300]
    result['date'] = (root.findtext(DC + 'date') or '').strip()[:100]
    try:
        result['url'] = _canonical_url(root.findtext(DC + 'source'))
    except ValueError:
        pass
    return result


def _paragraphs(document):
    root = _read_xml(document, 'word/document.xml', MAX_BODY_BYTES)
    body = root.find(WORD + 'body')
    if root.tag != WORD + 'document' or body is None:
        raise ValueError('Unsupported Word document body.')
    paragraphs = []
    notice = ''
    inline = {WORD + 'tab': '\t', WORD + 'br': '\n', WORD + 'cr': '\n'}
    for number, paragraph in enumerate(body.findall(WORD + 'p'), 1):
        if number > MAX_PARAGRAPHS:
            notice = 'Search covers the first 2,000 main-body paragraphs.'
            break
        # Include hyperlinks in their original position without following the links.
        runs = [run for child in paragraph for run in (
            [child] if child.tag == WORD + 'r' else
            child.findall(WORD + 'r') if child.tag == WORD + 'hyperlink' else []
        )]
        text = ''.join(
            (part.text or '') if part.tag == WORD + 't' else inline.get(part.tag, '')
            for run in runs for part in run
        )
        if not text.strip():
            continue
        if len(text.encode('utf-8')) > MAX_PASSAGE_BYTES:
            notice = 'Some paragraphs exceed the passage size limit and were omitted.'
            continue
        paragraphs.append(dict(number=number, text=text))
    return paragraphs, notice


def preview_word_document(data):
    if not 0 < len(data) <= MAX_DOCUMENT_BYTES:
        raise ValueError('Choose a Word document no larger than 8 MiB.')
    try:
        with ZipFile(io.BytesIO(data)) as document:
            if 'word/document.xml' not in document.namelist() or '[Content_Types].xml' not in document.namelist():
                raise ValueError('Choose a valid Word .docx document.')
            metadata = _metadata(document)
            try:
                paragraphs, notice = _paragraphs(document)
            except (ValueError,) + XML_ERRORS:
                paragraphs, notice = [], 'Could not preview the document body. You can still use the details below.'
    except XML_ERRORS as exc:
        raise ValueError('Could not read this Word document.') from exc
    return dict(metadata=metadata, paragraphs=paragraphs, passage_notice=notice)
