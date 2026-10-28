"""Verify the neural graph against real backend records and browser interaction."""

import json

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    with httpx.Client(base_url="http://localhost:8000") as client:
        sid = client.get("/api/spaces").json()[0]["id"]
        graph = client.get(f"/api/spaces/{sid}/mind/graph").json()
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(f"localStorage.setItem('rm-space', {json.dumps(sid)})")
        page.goto("http://localhost:5173/?view=group")
        expect(page.get_by_role("heading", name="Group Mind", exact=True)).to_be_visible()
        expect(page.locator("[data-neuron]")).to_have_count(len(graph["nodes"]))
        expect(page.locator(".synapse")).to_have_count(len(graph["edges"]))
        assert page.locator(".neural-error").count() == 0
        page.screenshot(path="artifacts/neural-mind-desktop.png", full_page=True)

        discovery = page.get_by_role("button", name="Discovery: Red object 01", exact=True)
        discovery.click()
        expect(page.locator(".neural-node-header h3")).to_have_text("Red object 01")
        expect(page.locator(".neural-node-facts")).to_contain_text("Confidence")
        page.get_by_text("Inspect stored evidence", exact=True).click()
        expect(page.locator(".neural-raw pre")).to_contain_text("observed_by")
        page.screenshot(path="artifacts/neural-mind-evidence.png", full_page=True)

        page.get_by_role("button", name="Memories", exact=True).click()
        expect(page.get_by_role("button", name="Memories", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        page.get_by_role("textbox", name="Search neural network").fill("Scout-03")
        expect(page.locator(".neural-stage-top")).to_contain_text("MATCHING NEURONS")
        page.get_by_role("button", name="Clear neural search").click()
        page.get_by_role("button", name="All connections", exact=True).click()
        page.get_by_role("button", name="Zoom in neural network").click()
        expect(page.locator(".neural-map-controls")).to_contain_text("120%")
        page.get_by_role("button", name="Reset neural view").click()
        expect(page.locator(".neural-map-controls")).to_contain_text("100%")
        page.get_by_role("button", name="Pause signal animation").click()
        expect(page.get_by_role("button", name="Play signal animation")).to_be_visible()
        page.get_by_role("button", name="Play signal animation").click()

        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path="artifacts/neural-mind-mobile.png", full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.get_by_role("button", name="Robot: Scout-01", exact=True).focus()
        page.keyboard.press("Enter")
        expect(page.locator(".neural-node-header h3")).to_have_text("Scout-01")
        assert not errors, errors
        browser.close()
    print(f"PASS: {len(graph['nodes'])} real neurons, {len(graph['edges'])} valid connections")
    print(
        "PASS: provenance, filters, search, zoom, reset, animation, "
        "keyboard, mobile; 0 runtime errors"
    )


if __name__ == "__main__":
    main()
