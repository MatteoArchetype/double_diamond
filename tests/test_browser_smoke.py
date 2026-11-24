"""Small real-browser smoke tests for the local interface.

These tests start the real loopback server and use the real launch token. They
cover navigation only at the browser boundary; research invariants remain
covered by the Python and HTTP suites.
"""
import threading

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
