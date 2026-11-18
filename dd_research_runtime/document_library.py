"""Case-local original documents, separate from reviewed evidence."""
import hashlib
import heapq
import re
import sqlite3
from contextlib import closing

from .document_preview import MAX_PARAGRAPHS
from .file_preview import preview_file, EXTENSIONS, MEDIA
from pathlib import Path

MAX_DOCUMENTS = 20
SEARCH_LIMIT = 10
WORD_TOKEN = re.compile(r"[^\W_]+")


class DocumentLibrary:
    def __init__(self, path):
        if path.is_symlink():
            raise ValueError('Invalid document library file.')
        self.path = path

    def save(self, filename, data):
        if (not isinstance(filename, str) or not 1 <= len(filename) <= 200
                or Path(filename).suffix.lower() not in EXTENSIONS or re.search(r'[/\\\x00-\x1f\x7f]', filename)):
            raise ValueError('Choose a supported file with a valid filename.')
        preview = preview_file(filename, data)
        if not preview.get('media') and not preview['paragraphs'] and not any(preview['metadata'].values()) and not filename.lower().endswith('.pdf'):
            raise ValueError('This file has no readable document details or main-body text.')
        digest = hashlib.sha256(data).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS documents (digest TEXT UNIQUE, filename TEXT, data BLOB)')
            saved = db.execute('SELECT filename FROM documents WHERE digest = ?', (digest,)).fetchone()
            if saved:
                filename = saved[0]
            else:
                if db.execute('SELECT COUNT(*) FROM documents').fetchone()[0] >= MAX_DOCUMENTS:
                    raise ValueError('This case already has 20 saved files.')
                db.execute('INSERT INTO documents VALUES (?, ?, ?)', (digest, filename, data))
        return dict(id=digest, filename=filename, **preview)

    def attach_transcript(self, digest, filename, data):
        original, _ = self.original(digest)
        if Path(original).suffix.lower() not in MEDIA:
            raise ValueError('Attach transcripts to a saved recording.')
        if not isinstance(filename, str) or not 1 <= len(filename) <= 200 or Path(filename).suffix.lower() not in {'.vtt', '.srt'} or re.search(r'[/\\\x00-\x1f\x7f]', filename):
            raise ValueError('Choose a WebVTT or SRT transcript.')
        preview_file(filename, data)
        checksum = hashlib.sha256(data).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS transcripts (media TEXT PRIMARY KEY, filename TEXT, data BLOB, digest TEXT)')
            row = db.execute('SELECT digest FROM transcripts WHERE media = ?', (digest,)).fetchone()
            if row and row[0] != checksum:
                raise ValueError('This recording already has a transcript. Save a revised transcript as a separate source file to review another version.')
            if not row:
                db.execute('INSERT INTO transcripts VALUES (?, ?, ?, ?)', (digest, filename, data, checksum))
        return self.preview(digest)

    def list(self):
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'documents'").fetchone():
                return []
            return [dict(id=digest, filename=filename) for digest, filename in db.execute(
                'SELECT digest, filename FROM documents ORDER BY rowid'
            )]

    def original(self, digest):
        if not re.fullmatch(r'[0-9a-f]{64}', digest) or not self.path.exists():
            raise ValueError('Saved document not found in this case.')
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            row = db.execute('SELECT filename, data FROM documents WHERE digest = ?', (digest,)).fetchone()
        if not row:
            raise ValueError('Saved document not found in this case.')
        filename, data = row
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Saved document integrity check failed.')
        return filename, data

    def preview(self, digest):
        filename, data = self.original(digest)
        result = dict(id=digest, filename=filename, **preview_file(filename, data))
        if result.get('media'):
            with closing(sqlite3.connect(self.path)) as db:
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='transcripts'").fetchone()
                row = db.execute('SELECT filename, data, digest FROM transcripts WHERE media = ?', (digest,)).fetchone() if exists else None
            if row:
                name, payload, checksum = row
                if hashlib.sha256(payload).hexdigest() != checksum:
                    raise ValueError('Transcript integrity check failed.')
                result.update(preview_file(name, payload))
                result.update(transcript_sha256=checksum, media=True, transcript_filename=name)
        return result

    def context(self, digest, number):
        """Return the verified match and available paragraphs within two positions."""
        if type(number) is not int or not 1 <= number <= MAX_PARAGRAPHS:
            raise ValueError('Choose a valid paragraph number.')
        result = self.preview(digest)
        paragraphs = [
            paragraph for paragraph in result['paragraphs']
            if abs(paragraph['number'] - number) <= 2
        ]
        if not any(paragraph['number'] == number for paragraph in paragraphs):
            raise ValueError('This paragraph is unavailable in the saved document preview.')
        return dict(filename=result['filename'], number=number, paragraphs=paragraphs,
                    passage_notice=result['passage_notice'],
                    location=next((p.get('location', f'Main-body paragraph {number}') for p in paragraphs if p['number']==number)),
                    transcript_sha256=result.get('transcript_sha256'))

    def search(self, query, mode="phrase"):
        """Find passages in this case's saved, integrity-checked originals."""
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
            raise ValueError('Enter a word or phrase of up to 200 characters.')
        if mode not in ('phrase', 'keywords'):
            raise ValueError('Choose exact phrase or keyword search.')
        term = query.strip().casefold()
        keywords = list(dict.fromkeys(WORD_TOKEN.findall(term))) if mode == 'keywords' else []
        if mode == 'keywords' and not keywords:
            raise ValueError('Enter at least one keyword with letters or numbers.')
        matches, incomplete = [], []
        total = 0
        documents = self.list()
        for item in documents:
            try:
                preview = self.preview(item['id'])
            except ValueError:
                incomplete.append(item['filename'])
                continue
            if preview['passage_notice']:
                incomplete.append(item['filename'])
            for paragraph in preview['paragraphs']:
                text = paragraph['text'].casefold()
                phrase_match = term in text
                matched = []
                if mode == 'keywords':
                    words = set(WORD_TOKEN.findall(text))
                    matched = [word for word in keywords if word in words]
                    if not matched:
                        continue
                elif not phrase_match:
                    continue
                total += 1
                result = dict(**item, **paragraph, metadata=preview['metadata'])
                if mode == 'keywords':
                    result['matched_keywords'] = matched
                # Prefer distinct keyword coverage, then the phrase, then reading order.
                rank = (len(matched), phrase_match, -total)
                entry = (rank, result)
                if len(matches) < SEARCH_LIMIT:
                    heapq.heappush(matches, entry)
                elif rank > matches[0][0]:
                    heapq.heapreplace(matches, entry)
        return dict(matches=[result for _, result in sorted(matches, reverse=True)],
                    total=total, document_count=len(documents), incomplete=incomplete)
