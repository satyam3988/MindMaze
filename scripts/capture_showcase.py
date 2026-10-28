"""Capture genuine application screens during an authenticated live mission."""

import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "docs/images"
    with httpx.Client(base_url="http://localhost:8000", timeout=10) as client:
        sid = client.get("/api/spaces").json()[0]["id"]
        response = client.post(
            f"/api/spaces/{sid}/commands",
            json={
                "text": (
                    "Find all red objects. Split up and avoid searching the same places twice."
                )
            },
        )
        response.raise_for_status()
        mid = response.json()["id"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1920, "height": 1280}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(f"localStorage.setItem('rm-space', {json.dumps(sid)})")
            page.goto("http://localhost:5173")
            page.get_by_text("SYSTEM LIVE", exact=True).wait_for()
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                mission = client.get(f"/api/missions/{mid}").json()
                if mission["state"] == "executing":
                    break
                assert mission["state"] != "failed", mission["error"]
                page.wait_for_timeout(250)
            else:
                raise RuntimeError("Mission did not begin executing")
            page.wait_for_timeout(2200)
            page.screenshot(path=str(output / "mission-control-live.png"))
            page.locator(".feeds").screenshot(path=str(output / "robot-camera-feeds.png"))
            page.get_by_role("button", name="Group Mind").click()
            expect(page.locator("[data-neuron]").first).to_be_visible()
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(output / "neural-group-mind.png"))
            page.get_by_role("button", name="Discovery: Red object 01", exact=True).click()
            page.get_by_text("Inspect stored evidence", exact=True).click()
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(output / "discovery-evidence.png"))
            page.get_by_role("button", name="Mission control", exact=True).click()
            while time.monotonic() < deadline:
                mission = client.get(f"/api/missions/{mid}").json()
                if mission["state"] in ("complete", "failed"):
                    break
                page.wait_for_timeout(500)
            assert mission["state"] == "complete", mission.get("error")
            expect(page.locator(".result")).to_be_visible()
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(output / "mission-complete.png"))
            assert not errors, errors
            browser.close()
        print(
            json.dumps(
                {
                    "mission": mid,
                    "result": mission["result"],
                    "screenshots": 5,
                    "browser_errors": errors,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
