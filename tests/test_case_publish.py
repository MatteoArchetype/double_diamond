"""Publishing a case must not depend on POSIX directory replacement.

Windows refuses ``os.replace`` when both sides are directories, with
``PermissionError: [WinError 5]``. These tests emulate that refusal on any
platform so the publish path cannot quietly regress to the POSIX-only shape.
"""
import os
from pathlib import Path
import pytest
from dd_research_runtime import case_publish
from dd_research_runtime.local_app import Workspace
from test_local_app import create, request, source


def refuse_directory_replace(monkeypatch):
    """Make ``os.replace`` behave the way Windows does for directories."""
    real = os.replace

    def replace(source, destination):
        if Path(destination).is_dir() and Path(destination).exists():
            raise PermissionError(13, 'Access is denied')
        return real(source, destination)

    monkeypatch.setattr(os, 'replace', replace)


def test_new_case_publishes_without_replacing_a_directory(tmp_path, monkeypatch):
    refuse_directory_replace(monkeypatch)
    w = Workspace(tmp_path / 'workspace')
    cid = create(w)
    assert [c['case_id'] for c in w.cases()] == [cid]
    assert w.view(cid)['revision'] == 1
    assert not any(p.name.startswith('.reserve-') for p in w.path.iterdir())


def test_restored_case_publishes_without_replacing_a_directory(tmp_path, monkeypatch):
    w = Workspace(tmp_path / 'workspace')
    cid = create(w)
    request(w, cid, 'source', source(), request_id='fixture')
    revision = w.view(cid)['revision']
    data, _ = w.backup(cid, revision)
    preview = w.inspect_backup(data)
    refuse_directory_replace(monkeypatch)
    result = w.restore_backup(data, preview['checkpoint_digest'])
    assert result['case_id'] != cid
    assert len(w.cases()) == 2
    assert not any(p.name.startswith('.reserve-') for p in w.path.iterdir())


def test_publish_refuses_an_existing_case_and_drops_its_claim(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    staged = tmp_path / 'staged'
    staged.mkdir()
    (staged / 'case-info.json').write_text('{}')
    destination = workspace / ('b' * 32)
    destination.mkdir()
    reservation = case_publish.reserve(workspace, destination.name)
    with pytest.raises(FileExistsError):
        case_publish.publish(staged, destination, reservation)
    assert not reservation.exists() and staged.exists() and destination.is_dir()
    assert list(destination.iterdir()) == []


def test_a_claim_left_by_a_crashed_creation_is_not_a_case(tmp_path):
    w = Workspace(tmp_path / 'workspace')
    (w.path / ('.reserve-' + 'c' * 32)).write_text('')
    assert w.catalog() == dict(cases=[], unavailable_cases=[])
    cid = create(w)
    assert [c['case_id'] for c in w.cases()] == [cid]


def test_an_interrupted_publish_leaves_no_partial_case(tmp_path):
    w = Workspace(tmp_path / 'workspace')

    def fault(name):
        if name == 'before_publication':
            raise RuntimeError('simulated interruption')

    with pytest.raises(RuntimeError):
        w.create(dict(title='Synthetic interruption', question='What remains unknown?',
                      scope='Test only', max_visits=8, max_alternatives=3), _fault=fault)
    assert w.cases() == [] and list(w.path.iterdir()) == []


def test_two_creations_cannot_claim_the_same_identifier(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    first = case_publish.reserve(workspace, 'd' * 32)
    with pytest.raises(FileExistsError, match='already in use'):
        case_publish.reserve(workspace, 'd' * 32)
    assert first.exists()


def test_publishing_survives_a_claim_that_already_vanished(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    staged = tmp_path / 'staged'
    staged.mkdir()
    (staged / 'case-info.json').write_text('{}')
    reservation = case_publish.reserve(workspace, 'e' * 32)
    reservation.unlink()
    destination = case_publish.publish(staged, workspace / ('e' * 32), reservation)
    assert (destination / 'case-info.json').read_text() == '{}'


def test_a_fault_after_publication_keeps_the_complete_case(tmp_path):
    w = Workspace(tmp_path / 'workspace')

    def fault(name):
        if name == 'after_publication':
            raise RuntimeError('simulated response failure')

    with pytest.raises(RuntimeError):
        w.create(dict(title='Synthetic response failure', question='Was it saved?',
                      scope='Test only', max_visits=8, max_alternatives=3), _fault=fault)
    assert [c['title'] for c in w.cases()] == ['Synthetic response failure']
    assert not any(p.name.startswith('.reserve-') for p in w.path.iterdir())
