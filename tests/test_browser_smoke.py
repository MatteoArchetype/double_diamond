"""Small real-browser smoke tests for the local interface.

These tests start the real loopback server and use the real launch token. They
cover navigation only at the browser boundary; research invariants remain
covered by the Python and HTTP suites.
"""
import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from dd_research_runtime.local_app import LocalServer, Workspace


pytest.importorskip("playwright.sync_api")


@pytest.fixture
def browser_server(tmp_path):
    server = LocalServer(Workspace(tmp_path / "workspace"), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def browser_page(browser_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip("Chromium is not installed: " + str(exc).splitlines()[0])
        page = browser.new_page()
        page.goto(browser_server.url)
        yield page
        browser.close()


def test_home_loads_and_starts_a_research_case(browser_page):
    browser_page.wait_for_selector("#workspace-home-title")
    assert browser_page.get_by_role(
        "heading", name="Turn a question into a traceable research decision."
    ).is_visible()
    assert browser_page.get_by_role("heading", name="Workspace health").is_visible()
    assert browser_page.get_by_text("Writable", exact=True).is_visible()

    browser_page.get_by_role("button", name="Start a research case").click()
    browser_page.get_by_label("What do you want to understand?").fill(
        "How might browser navigation affect research workflows?"
    )
    browser_page.get_by_label("Case name").fill("Browser smoke case")
    browser_page.get_by_role("button", name="Start research").click()

    browser_page.wait_for_selector("#research-case-title")
    assert browser_page.locator("#research-case-title").inner_text() == "Browser smoke case"
    assert "Discover" in browser_page.locator(".phase-strip").inner_text()
    assert browser_page.get_by_role("button", name="Sources", exact=True).is_visible()


def test_trashed_case_can_be_restored_from_the_browser(browser_page):
    browser_page.wait_for_selector("#workspace-home-title")
    browser_page.get_by_role("button", name="Start a research case").click()
    browser_page.get_by_label("What do you want to understand?").fill(
        "How might recovery preserve research?"
    )
    browser_page.get_by_label("Case name").fill("Recoverable browser case")
    browser_page.get_by_role("button", name="Start research").click()
    browser_page.wait_for_selector("#research-case-title")

    browser_page.get_by_text("Rename or remove this case").click()
    browser_page.get_by_label("Type the exact title to confirm").fill(
        "Recoverable browser case"
    )
    browser_page.get_by_role("button", name="Move this case to trash").click()
    browser_page.wait_for_selector("#workspace-home-title")

    browser_page.get_by_role("button", name="Trash (1)").click()
    browser_page.get_by_role("heading", name="Recoverable browser case").wait_for()
    browser_page.get_by_role("button", name="Restore this case").click()

    browser_page.wait_for_selector("#research-case-title")
    assert browser_page.locator("#research-case-title").inner_text() == "Recoverable browser case"


def test_synthetic_learning_example_opens_without_real_source_claims(browser_page):
    browser_page.wait_for_selector("#workspace-home-title")
    browser_page.get_by_role("button", name="Open practice example").click()

    browser_page.wait_for_selector("#research-case-title")
    assert "Synthetic learning example" in browser_page.locator(".hero").inner_text()
    app_text = browser_page.locator("#app").inner_text().lower()
    assert "synthetic evidence" in app_text
    assert "simulated" in app_text


def test_case_checkpoint_can_be_downloaded_and_restored_separately(
    browser_page, browser_server, tmp_path
):
    browser_page.wait_for_selector("#workspace-home-title")
    browser_page.get_by_role("button", name="Start a research case").click()
    browser_page.get_by_label("What do you want to understand?").fill(
        "How might backup recovery preserve research?"
    )
    browser_page.get_by_label("Case name").fill("Browser backup smoke case")
    browser_page.get_by_role("button", name="Start research").click()
    browser_page.wait_for_selector("#research-case-title")

    original_id = parse_qs(urlparse(browser_page.url).query)["case"][0]
    original_before = browser_server.workspace.view(original_id)
    original_database = (
        browser_server.workspace.path / original_id / "research.sqlite"
    )
    original_digest = hashlib.sha256(original_database.read_bytes()).digest()
    browser_page.get_by_text("More research tools").click()
    browser_page.get_by_role("button", name="Save a copy").click()
    for label in (
        "Total files for this case",
        "Research database included in checkpoint",
        "Original files and transcripts excluded",
        "Unsaved drafts excluded",
        "Saved source shortlist excluded",
    ):
        assert browser_page.get_by_text(label, exact=True).is_visible()

    checkpoint = tmp_path / "browser-checkpoint.zip"
    with browser_page.expect_download() as download_event:
        browser_page.get_by_role("button", name="Download case checkpoint").click()
    download_event.value.save_as(checkpoint)
    assert checkpoint.is_file() and checkpoint.stat().st_size > 0

    browser_page.get_by_role(
        "button", name="Restore a checkpoint as a separate case"
    ).click()
    browser_page.get_by_label("Choose checkpoint ZIP").set_input_files(checkpoint)
    browser_page.get_by_role("button", name="Inspect selected checkpoint").click()
    browser_page.get_by_role("heading", name="Checkpoint inspection").wait_for()
    assert browser_page.get_by_role("main").get_by_text(
        "Browser backup smoke case", exact=True
    ).is_visible()
    browser_page.get_by_role("button", name="Cancel restore").click()

    repository = Path(__file__).resolve().parents[1]
    inspect_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dd_research_runtime.checkpoint_cli",
            "inspect",
            str(checkpoint),
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(inspect_result.stdout)["ok"] is True
    restore_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dd_research_runtime.checkpoint_cli",
            "restore-case",
            str(checkpoint),
            str(browser_server.workspace.path),
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    restored_data = json.loads(restore_result.stdout)
    assert restored_data["approval_granted"] is False
    restored_id = restored_data["case_id"]
    assert restored_id != original_id
    restored = browser_server.workspace.view(restored_id)
    assert restored["meta"]["restored_checkpoint"] is True
    assert restored["state"] == original_before["state"]
    assert restored["revision"] == restored_data["state_revision"]
    assert (restored["revision"], restored["ledger_revision"]) == (
        original_before["revision"],
        original_before["ledger_revision"],
    )
    assert browser_server.workspace.view(original_id) == original_before
    assert hashlib.sha256(original_database.read_bytes()).digest() == original_digest
    assert {case["case_id"] for case in browser_server.workspace.cases()} == {
        original_id,
        restored_id,
    }

    browser_page.get_by_role("button", name="Refresh saved research").click()
    restored_button = browser_page.get_by_role(
        "button", name="Restored · Browser backup smoke case", exact=True
    )
    restored_button.wait_for()
    restored_button.click()
    browser_page.get_by_role(
        "heading", name="Restored · Browser backup smoke case", exact=True
    ).wait_for()
    assert browser_page.get_by_text("Restored copy", exact=True).is_visible()

    browser_page.get_by_role(
        "button", name="Browser backup smoke case", exact=True
    ).click()
    browser_page.get_by_role(
        "heading", name="Browser backup smoke case", exact=True
    ).wait_for()
    assert browser_page.locator("#research-case-title").inner_text() == (
        "Browser backup smoke case"
    )
