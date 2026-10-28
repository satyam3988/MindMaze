"""Run a real mission and verify that persisted evidence grows the visible neural graph."""

import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    with httpx.Client(base_url="http://localhost:8000", timeout=10) as client:
        sid = client.get("/api/spaces").json()[0]["id"]
        initial = client.get(f"/api/spaces/{sid}/mind/graph").json()
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(f"localStorage.setItem('rm-space', {json.dumps(sid)})")
            page.goto("http://localhost:5173/?view=group")
            expect(page.locator("[data-neuron]")).to_have_count(len(initial["nodes"]))
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
            print("Real mission started:", mid, flush=True)
            page.wait_for_function(
                "count => document.querySelectorAll('[data-neuron]').length > count",
                arg=len(initial["nodes"]),
                timeout=90000,
            )
            expect(page.locator(".new-evidence").first).to_be_visible()
            page.screenshot(path="artifacts/neural-mind-live.png", full_page=True)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                mission = client.get(f"/api/missions/{mid}").json()
                if mission["state"] in ("complete", "failed"):
                    break
                page.wait_for_timeout(500)
            assert mission["state"] == "complete", mission.get("error")
            final = client.get(f"/api/spaces/{sid}/mind/graph").json()
            expect(page.locator("[data-neuron]")).to_have_count(len(final["nodes"]))
            page.screenshot(path="artifacts/neural-mind-completed.png", full_page=True)
            assert len(final["nodes"]) > len(initial["nodes"])
            assert len(final["edges"]) > len(initial["edges"])
            assert mission["result"]["unique_objects"] == 3
            assert mission["result"]["coverage"] == 1
            assert not errors, errors
            report = {
                "status": "passed",
                "mission_id": mid,
                "neurons_before": len(initial["nodes"]),
                "neurons_after": len(final["nodes"]),
                "connections_before": len(initial["edges"]),
                "connections_after": len(final["edges"]),
                "result": mission["result"],
                "browser_errors": errors,
            }
            Path("artifacts/neural-growth.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report, indent=2), flush=True)
            browser.close()


if __name__ == "__main__":
    main()
