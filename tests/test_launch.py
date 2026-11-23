"""Launch behaviour: where the workspace lives and whether the browser is opened."""
from pathlib import Path

import pytest

from dd_research_runtime import local_app


@pytest.fixture
def quiet_server(monkeypatch):
    """Create the real server object but return from serve_forever immediately."""
    monkeypatch.setattr(local_app.LocalServer, 'serve_forever', lambda self: None)


def test_default_workspace_is_beside_the_application_not_the_launch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = local_app._parse_args([])
    expected = Path(local_app.__file__).resolve().parent.parent / 'research-workspace'
    assert Path(args.workspace) == expected
    assert not str(args.workspace).startswith(str(tmp_path))


def test_explicit_workspace_still_wins(tmp_path):
    args = local_app._parse_args(['--workspace', str(tmp_path / 'mine')])
    assert Path(args.workspace) == tmp_path / 'mine'


def test_browser_opens_with_the_private_link_by_default(tmp_path, monkeypatch, quiet_server, capsys):
    opened = []
    monkeypatch.setattr(local_app.webbrowser, 'open', lambda url: opened.append(url))
    local_app.main(['--workspace', str(tmp_path / 'ws')])
    printed = capsys.readouterr().out
    assert len(opened) == 1
    assert opened[0].startswith('http://127.0.0.1:') and '#token=' in opened[0]
    assert opened[0] in printed  # the same link is still printed for copying


def test_no_browser_flag_only_prints_the_link(tmp_path, monkeypatch, quiet_server, capsys):
    opened = []
    monkeypatch.setattr(local_app.webbrowser, 'open', lambda url: opened.append(url))
    local_app.main(['--workspace', str(tmp_path / 'ws'), '--no-browser'])
    assert opened == []
    assert '#token=' in capsys.readouterr().out


def test_browser_failure_does_not_stop_the_app(tmp_path, monkeypatch, quiet_server, capsys):
    def broken(url):
        raise RuntimeError('no browser available')
    monkeypatch.setattr(local_app.webbrowser, 'open', broken)
    local_app.main(['--workspace', str(tmp_path / 'ws')])
    assert '#token=' in capsys.readouterr().out
