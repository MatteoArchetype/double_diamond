import io
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from dd_research_runtime import local_app, source_search


def test_search_returns_only_safe_bibliographic_leads(monkeypatch):
    def open_request(request, timeout):
        url = urlsplit(request.full_url)
        assert (url.scheme, url.netloc, url.path) == ('https', 'api.crossref.org', '/works')
        assert parse_qs(url.query)['query.bibliographic'] == ['urban heat & trees']
        assert timeout == 8
        entry = {'DOI': '10.1234/a?b', 'title': ['Urban shade'], 'publisher': 'Example Press',
                 'author': [{'given': 'Ada', 'family': 'Example'}, {'given': 'Ben', 'family': 'Reviewer'}],
                 'published-print': {'date-parts': [[2025, 6, 12]]},
                 'type': 'journal-article',
                 'URL': 'javascript:alert(1)', 'abstract': 'Unreviewed'}
        return io.BytesIO(json.dumps({'message': {'items': [
            entry, entry, {'DOI': 'https://evil.example', 'title': ['Invalid']},
        ]}}).encode())

    monkeypatch.setattr(source_search, 'build_opener', lambda *_: SimpleNamespace(open=open_request))
    assert source_search.search_publications(' urban heat & trees ') == [
        {'title': 'Urban shade', 'publisher': 'Example Press', 'url': 'https://doi.org/10.1234/a%3Fb',
         'authors': 'Ada Example; Ben Reviewer', 'date': '2025-06-12', 'type': 'journal-article'},
    ]


@pytest.mark.parametrize('query', ['', ' '*5, 'x'*301, ['trees']])
def test_invalid_query_is_never_sent(query, monkeypatch):
    monkeypatch.setattr(source_search, 'build_opener', lambda *_: pytest.fail('Network contacted'))
    with pytest.raises(ValueError, match='300 characters'):
        source_search.search_publications(query)


def test_search_filters_are_sent_to_crossref(monkeypatch):
    def open_request(request, timeout):
        assert timeout == 8
        assert parse_qs(urlsplit(request.full_url).query)['filter'] == [
            'from-pub-date:2024-01-01,until-pub-date:2025-12-31,type:journal-article'
        ]
        return io.BytesIO(json.dumps({'message': {'items': []}}).encode())

    monkeypatch.setattr(source_search, 'build_opener', lambda *_: SimpleNamespace(open=open_request))
    assert source_search.search_publications(
        'urban heat', from_date='2024-01-01', to_date='2025-12-31',
        publication_type='journal-article') == []


@pytest.mark.parametrize('kwargs, message', [
    ({'from_date': 'tomorrow'}, 'YYYY'),
    ({'to_date': '2025-13-01'}, 'YYYY'),
    ({'publication_type': 'patent'}, 'publication type'),
    ({'from_date': '2025', 'to_date': '2024'}, 'end date'),
])
def test_invalid_search_filters_are_rejected_before_network(kwargs, message, monkeypatch):
    monkeypatch.setattr(source_search, 'build_opener', lambda *_: pytest.fail('Network contacted'))
    with pytest.raises(ValueError, match=message):
        source_search.search_publications('urban heat', **kwargs)


def test_provider_failure_is_reported(monkeypatch):
    def unavailable(*args, **kwargs):
        raise TimeoutError('provider error')

    monkeypatch.setattr(source_search, 'build_opener', lambda *_: SimpleNamespace(open=unavailable))
    with pytest.raises(ValueError, match='search is unavailable'):
        source_search.search_publications('urban trees')


@pytest.mark.parametrize('authorized', [True, False])
def test_search_route_is_explicit_and_read_only(monkeypatch, authorized):
    body = b'{"query":"urban trees"}'
    origin = 'http://127.0.0.1:12345'
    headers = {'Host': '127.0.0.1:12345', 'Origin': origin,
               'Content-Type': 'application/json', 'Content-Length': str(len(body))}
    if authorized:
        headers['Authorization'] = 'Bearer private-token'
    calls = []
    monkeypatch.setattr(local_app, 'search_publications',
                        lambda query, **filters: calls.append((query, filters)) or [])
    replies = []
    handler = object.__new__(local_app.Handler)
    handler.server = SimpleNamespace(origin=origin, token='private-token')
    handler.path = '/api/source-search'
    handler.headers = headers
    handler.rfile = io.BytesIO(body)
    handler._reply = lambda status, result: replies.append((status, result))
    handler.do_POST()
    assert replies[0][0] == (200 if authorized else 403)
    assert calls == ([('urban trees', {
        'from_date': '', 'to_date': '', 'publication_type': '',
    })] if authorized else [])
