"""Bounded previews of originals. Uploaded text is data, never instructions."""
import io
import re
from pathlib import Path

from .document_preview import preview_word_document, MAX_PARAGRAPHS
from .payload_limits import MAX_PASSAGE_BYTES

MAX_FILE_BYTES = 64 * 1024 * 1024
MEDIA = {'.mp4', '.mov', '.webm', '.mp3', '.m4a', '.wav', '.ogg'}
TEXT = {'.txt', '.md', '.vtt', '.srt'}
EXTENSIONS = MEDIA | TEXT | {'.pdf', '.docx'}


def preview_file(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS or not 0 < len(data) <= MAX_FILE_BYTES:
        raise ValueError('Choose a supported file no larger than 64 MiB.')
    if suffix == '.docx':
        return preview_word_document(data)
    metadata = dict(title='', publisher='', date='', url='')
    paragraphs, notice = [], ''
    if suffix in MEDIA:
        valid = ((suffix in {'.mp4', '.mov', '.m4a'} and data[4:8] == b'ftyp')
                 or (suffix == '.webm' and data.startswith(b'\x1aE\xdf\xa3'))
                 or (suffix == '.wav' and data.startswith(b'RIFF') and data[8:12] == b'WAVE')
                 or (suffix == '.ogg' and data.startswith(b'OggS'))
                 or (suffix == '.mp3' and (data.startswith(b'ID3') or
                     (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224))))
        if not valid:
            raise ValueError('The file does not match its recording format.')
        return dict(metadata=metadata, paragraphs=[], passage_notice=
                    'Save this recording and attach a WebVTT or SRT transcript to search spoken passages. Automatic transcription is unavailable.',
                    media=True)
    if suffix == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError('PDF support requires the pypdf package. Install requirements.txt.') from exc
        try:
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ValueError('Upload an unlocked PDF.')
            if len(reader.pages) > 500:
                raise ValueError('PDFs support up to 500 pages.')
            info = reader.metadata
            if info:
                metadata.update(title=str(info.title or '')[:500], publisher=str(info.author or '')[:300])
            total = 0
            for page, item in enumerate(reader.pages, 1):
                text = item.extract_text() or ''
                total += len(text.encode('utf8'))
                if total > 2 * 1024 * 1024:
                    raise ValueError('PDF extracted text exceeds 2 MiB.')
                for block in text.split('\n\n'):
                    if block.strip():
                        paragraphs.append(dict(number=len(paragraphs)+1, text=block.strip(), location=f'Page {page}'))
            notice = 'PDF text extraction can change reading order. Check each passage against the original page. Scanned pages need OCR before text search.'
        except Exception as exc:
            raise ValueError('Could not read PDF: ' + str(exc)[:180]) from exc
    else:
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Text files support up to 2 MiB.')
        try:
            text = data.decode('utf-8-sig')
        except UnicodeError as exc:
            raise ValueError('Save text and transcripts as UTF-8.') from exc
        if '\x00' in text:
            raise ValueError('Choose a readable text file.')
        if suffix in {'.vtt', '.srt'}:
            timestamp = re.compile(r'(?m)^(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})[^\n]*\n([^\n]+(?:\n(?!\s*\n)[^\n]+)*)')
            def seconds(value):
                parts = value.replace(',', '.').split(':')
                minute, second = int(parts[-2]), float(parts[-1])
                if minute >= 60 or second >= 60:
                    raise ValueError('Invalid transcript timestamp.')
                return (int(parts[0]) * 3600 if len(parts) == 3 else 0) + minute * 60 + second
            for match in timestamp.finditer(text):
                if seconds(match[2]) <= seconds(match[1]):
                    raise ValueError('Transcript cues must end after they start.')
                paragraphs.append(dict(number=len(paragraphs)+1, text=match[3].strip(),
                                       location=match[1]+'–'+match[2]))
            if not paragraphs:
                raise ValueError('No timestamped transcript cues found. Use WebVTT or SRT.')
            notice = 'Transcript supplied by the researcher. Check its words and timestamps against the recording.'
        else:
            for line, block in enumerate(text.splitlines(), 1):
                if block.strip():
                    paragraphs.append(dict(number=len(paragraphs)+1, text=block, location=f'Line {line}'))
    if len(paragraphs) > MAX_PARAGRAPHS or any(len(p['text'].encode('utf8')) > MAX_PASSAGE_BYTES for p in paragraphs):
        raise ValueError('File exceeds the searchable passage limits. Split it into smaller files.')
    return dict(metadata=metadata, paragraphs=paragraphs, passage_notice=notice)
