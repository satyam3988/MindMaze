"""Exercise the running dashboard and save reviewable screenshots."""

import json

import httpx
from playwright.sync_api import sync_playwright


def main():
    sid = httpx.get("http://localhost:8000/api/spaces").json()[0]["id"]
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1536, "height": 1150}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(f"localStorage.setItem('rm-space', {json.dumps(sid)})")
        page.goto("http://localhost:5173")
        page.get_by_text("SYSTEM LIVE", exact=True).wait_for()
        page.get_by_role("heading", name="Mission control", exact=True).wait_for()
        page.locator(".member").first.wait_for()
        page.wait_for_timeout(1800)
        page.screenshot(path="artifacts/dashboard-desktop.png", full_page=True)
        page.locator(".member").nth(2).click()
        page.get_by_role("button", name="Deep Mind", exact=True).click()
        page.get_by_role("button", name="Camera", exact=True).click()
        page.get_by_role("button", name="Group Mind").click()
        page.get_by_role("heading", name="Group Mind", exact=True).wait_for()
        page.screenshot(path="artifacts/group-mind.png", full_page=True)
        page.get_by_role("button", name="Mission history", exact=True).click()
        page.get_by_role("heading", name="Mission history", exact=True).wait_for()
        page.get_by_role("button", name="Join space", exact=True).click()
        page.get_by_role("heading", name="Join a shared space").wait_for()
        page.get_by_role("button", name="Close", exact=True).click()
        page.get_by_role("button", name="Mission control", exact=True).click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path="artifacts/dashboard-mobile.png", full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
            "Horizontal overflow"
        )
        assert not errors, errors
        browser.close()
    print(
        "PASS: live connection, robot selection, mind tabs, "
        "group knowledge, history, dialog, mobile layout"
    )
    print("Browser runtime errors:", len(errors))


if __name__ == "__main__":
    main()
