"""Temporary research leads kept separately from reviewed evidence."""
import re
import sqlite3
from contextlib import closing
from urllib.parse import quote, unquote, urlsplit

from .analysis_transactions import _keys

MAX_LEADS = 100
DOI_URL = 'https://doi.org/'


def _canonical_url(url):
    error = 'Enter a complete HTTP or HTTPS source link without credentials.'
    if not isinstance(url, str):
        raise ValueError(error)
    url = url.strip()
    if not 1 <= len(url) <= 4096 or re.search(r'[\s\x00-\x1f\x7f\\]', url):
        raise ValueError(error)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError(error) from exc
    if (parts.scheme not in {'http', 'https'} or not parts.hostname
            or parts.username is not None or '%' in parts.netloc):
        raise ValueError(error)
    if parts.hostname == 'doi.org':
        doi = unquote(parts.path.removeprefix('/'))
        if (port not in {None, 80, 443} or parts.query or parts.fragment
                or not re.fullmatch(r'10\.[0-9]{4,9}/[^\s\x00-\x1f\x7f]{1,240}', doi)):
            raise ValueError('A valid publication DOI link is required.')
        return DOI_URL + quote(doi.lower(), safe='/')
    return parts._replace(netloc=parts.netloc.lower()).geturl()


class SourceShortlist:
    def __init__(self, path):
        if path.is_symlink():
            raise ValueError('Invalid shortlist file.')
        self.path = path

    def _rows(self, db):
        rows=[]
        columns={row[1] for row in db.execute('PRAGMA table_info(leads)')}
        extras=[name for name in ('authors','date','type') if name in columns]
        select=['url','title','publisher']+[name for name in extras]
        for row in db.execute('SELECT '+', '.join(select)+' FROM leads ORDER BY rowid'):
            lead=dict(row)
            for name in ('authors','date','type'):
                if lead.get(name):
                    continue
                lead.pop(name)
            rows.append(lead)
        return rows

    def read(self):
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'leads'").fetchone():
                return []
            return self._rows(db)

    def change(self, action, lead):
        if action == 'keep':
            _keys(lead, {'url', 'title', 'publisher'}, {'authors','date','type'})
            title, publisher = lead['title'], lead['publisher']
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 500:
                raise ValueError('A source title is required.')
            if not isinstance(publisher, str) or len(publisher) > 300:
                raise ValueError('Invalid publisher.')
            for name in ('authors','date','type'):
                if name in lead and not isinstance(lead[name],str):
                    raise ValueError('Invalid source metadata.')
            authors=lead.get('authors','')[:500]
            date=lead.get('date','')[:20]
            publication_type=lead.get('type','')[:100]
        elif action == 'remove':
            _keys(lead, {'url'})
        else:
            raise ValueError('Unknown shortlist action.')
        url = _canonical_url(lead['url'])
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            with db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS leads (url TEXT UNIQUE, title TEXT, publisher TEXT)')
                columns={row[1] for row in db.execute('PRAGMA table_info(leads)')}
                for name,kind in (('authors','TEXT'),('date','TEXT'),('type','TEXT')):
                    if name not in columns:
                        db.execute(f'ALTER TABLE leads ADD COLUMN {name} {kind}')
                if action == 'keep':
                    if not db.execute('SELECT 1 FROM leads WHERE url = ?', (url,)).fetchone():
                        if db.execute('SELECT COUNT(*) FROM leads').fetchone()[0] >= MAX_LEADS:
                            raise ValueError('This shortlist is full. Remove a lead before adding another.')
                        db.execute('INSERT INTO leads (url,title,publisher,authors,date,type) VALUES (?, ?, ?, ?, ?, ?)',
                                   (url,title.strip(),publisher.strip(),authors,date,publication_type))
                else:
                    db.execute('DELETE FROM leads WHERE url = ?', (url,))
                return self._rows(db)
