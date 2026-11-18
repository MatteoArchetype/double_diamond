from concurrent.futures import ThreadPoolExecutor

import pytest

from dd_research_runtime.local_app import Workspace
from test_local_app import create


def lead(suffix='first'):
    return dict(url='https://doi.org/10.1234/'+suffix, title='Candidate publication', publisher='Publisher')


def test_shortlist_is_case_local_durable_and_separate_from_evidence(tmp_path):
    workspace = Workspace(tmp_path)
    case = create(workspace)
    other = create(workspace)
    before = workspace.view(case)
    shortlist = workspace.shortlist(case)
    assert shortlist.read() == []
    assert not shortlist.path.exists()
    shortlist.change('keep', lead('FIRST'))
    shortlist.change('keep', lead())
    reopened = Workspace(tmp_path).shortlist(case)
    assert reopened.read() == [lead()]
    assert workspace.shortlist(other).read() == []
    assert workspace.view(case) == before
    assert reopened.change('remove', {'url': lead()['url']}) == []


def test_concurrent_keeps_preserve_distinct_leads(tmp_path):
    workspace = Workspace(tmp_path)
    case = create(workspace)
    candidates = [lead(str(n)) for n in range(10)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda item: workspace.shortlist(case).change('keep', item), candidates))
    assert {item['url'] for item in workspace.shortlist(case).read()} == {item['url'] for item in candidates}


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://doi.org@other.example/10.1234/a', 'https://doi.org/10.1234/%0Ax'])
def test_rejects_unsafe_links_without_creating_storage(tmp_path, url):
    workspace = Workspace(tmp_path)
    shortlist = workspace.shortlist(create(workspace))
    with pytest.raises(ValueError):
        shortlist.change('keep', dict(lead(), url=url))
    assert not shortlist.path.exists()


def test_manual_web_source_preserves_locator_and_remains_a_lead(tmp_path):
    workspace = Workspace(tmp_path)
    case = create(workspace)
    before = workspace.view(case)
    shortlist = workspace.shortlist(case)
    url = 'https://example.org/Reports/2025?edition=A#methods'
    candidate = dict(url=url, title='Municipal heat report', publisher='')
    assert shortlist.change('keep', dict(candidate, url=url.replace('example.org', 'EXAMPLE.ORG'))) == [candidate]
    assert shortlist.change('keep', candidate) == [candidate]
    assert Workspace(tmp_path).shortlist(case).read() == [candidate]
    assert workspace.view(case) == before
    assert shortlist.change('remove', {'url': url}) == []


@pytest.mark.parametrize('url', [
    'https://reader:secret@example.org/report',
    'https://example.org\\@other.example/report',
    'https://example.org:invalid/report',
    'https:///missing-host',
    'file:///tmp/source',
    '//example.org/report',
])
def test_manual_link_rejects_non_web_urls_and_ambiguous_authorities(tmp_path, url):
    workspace = Workspace(tmp_path)
    shortlist = workspace.shortlist(create(workspace))
    with pytest.raises(ValueError):
        shortlist.change('keep', dict(lead(), url=url))
    assert not shortlist.path.exists()
