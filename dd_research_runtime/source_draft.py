"""Case-local form drafts, separate from evidence and approvals."""
import json
import sqlite3
from contextlib import closing

from .analysis_transactions import _ids, _keys
from .payload_limits import MAX_FIELD_BYTES, MAX_PASSAGE_BYTES, MAX_SNAPSHOT_BYTES, text_bytes

DRAFT_FIELDS = {'title','publisher','url','published_at','group','passage','location','snapshot','rationale','synthetic'}


class _FormDraft:
    def __init__(self, path):
        if path.is_symlink():
            raise ValueError('Invalid research draft file.')
        self.path = path

    def read(self):
        if not self.path.exists():
            return dict(version=0, draft=None)
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'source_draft'").fetchone():
                return dict(version=0, draft=None)
            row = db.execute('SELECT version, draft FROM source_draft WHERE id = 1').fetchone()
            return dict(version=row[0], draft=json.loads(row[1])) if row else dict(version=0, draft=None)

    def write(self, expected_version, draft):
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Invalid draft version.')
        if draft is not None:
            self.validate(draft)
        payload = json.dumps(draft,ensure_ascii=False)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS source_draft (id INTEGER PRIMARY KEY, version INTEGER, draft TEXT)')
            row = db.execute('SELECT version FROM source_draft WHERE id = 1').fetchone()
            version = row[0] if row else 0
            if version != expected_version:
                raise RuntimeError('The saved draft changed in another view. Refresh the saved draft before replacing it.')
            db.execute('INSERT OR REPLACE INTO source_draft VALUES (1, ?, ?)',(version+1,payload))
        return dict(version=version+1,draft=draft)


class SourceDraft(_FormDraft):
    def validate(self, draft):
        _keys(draft,DRAFT_FIELDS)
        if type(draft['synthetic']) is not bool:
            raise ValueError('Invalid synthetic draft label.')
        for name in DRAFT_FIELDS - {'synthetic'}:
            value = draft[name]
            if not isinstance(value,str):
                raise ValueError('Draft fields must be text.')
            limit = {'passage':MAX_PASSAGE_BYTES,'snapshot':MAX_SNAPSHOT_BYTES}.get(name,MAX_FIELD_BYTES)
            text_bytes(value,limit,name)


class _VisitDraft(_FormDraft):
    def validate(self, draft):
        _keys(draft,self.text_fields | self.link_fields)
        _draft_links(draft, self.link_fields)
        _draft_text_fields(draft, self.text_fields)


class DiscoverDraft(_VisitDraft):
    text_fields = {'notes', 'perspectives', 'limitations', 'rationale'}
    link_fields = {'evidence_ids'}


class DefineDraft(_VisitDraft):
    text_fields = {'problem', 'criteria', 'rationale'}
    link_fields = {'claim_ids', 'uncertainty_ids'}


def _draft_text_fields(data, names):
    for name in names:
        value = data[name]
        if not isinstance(value, str):
            raise ValueError('Draft fields must be text.')
        text_bytes(value, MAX_PASSAGE_BYTES, name)


def _draft_links(data, names):
    for name in names:
        identifiers = _ids(data[name], name)
        if len(identifiers) > 1000:
            raise ValueError('Select at most 1,000 references per draft field.')
        for identifier in identifiers:
            text_bytes(identifier, MAX_FIELD_BYTES, 'reference identifier')


def _draft_rows(rows, minimum):
    if not isinstance(rows, list) or not minimum <= len(rows) <= 20:
        raise ValueError('Invalid number of draft rows.')
    return rows


class DevelopDraft(_FormDraft):
    def validate(self, draft):
        _keys(draft, {'record', 'rationale'})
        _draft_text_fields(draft, {'rationale'})
        record = draft['record']
        _keys(record, {'alternatives'})
        for row in _draft_rows(record['alternatives'], 2):
            text = {'alternative_id', 'hypothesis', 'test', 'limitations'}
            links = {'claim_ids', 'evidence_ids'}
            _keys(row, text | links)
            _draft_text_fields(row, text)
            _draft_links(row, links)


class DeliverDraft(_FormDraft):
    def validate(self, draft):
        _keys(draft, {'record', 'rationale'})
        _draft_text_fields(draft, {'rationale'})
        record = draft['record']
        text = {'selected_alternative_id', 'decision', 'summary', 'limitations'}
        _keys(record, text | {'evaluations', 'claim_ids', 'criterion_assessments'})
        _draft_text_fields(record, text)
        _draft_links(record, {'claim_ids'})
        for row in _draft_rows(record['evaluations'], 1):
            text = {'evaluation_id', 'alternative_id', 'method', 'outcome', 'limitations'}
            _keys(row, text | {'evidence_ids'})
            _draft_text_fields(row, text)
            _draft_links(row, {'evidence_ids'})
        criteria = record['criterion_assessments']
        if not isinstance(criteria, list) or len(criteria) > 1000:
            raise ValueError('Invalid number of draft criteria.')
        for index,row in enumerate(criteria):
            text = {'outcome', 'rationale', 'next_research'}
            _keys(row, text | {'criterion_index', 'evaluation_ids'})
            if type(row['criterion_index']) is not int or row['criterion_index'] != index:
                raise ValueError('Invalid draft criterion index.')
            _draft_text_fields(row, text)
            _draft_links(row, {'evaluation_ids'})
