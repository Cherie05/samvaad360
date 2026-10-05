"""Rehearse the running synthetic demo in a fresh isolated headless browser.

Requires a fresh Ananya pending action. This mutates only the local synthetic
demo through its UI; it does not use an existing signed-in browser profile.
"""
import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True, choices=["TEST-LOCAL-DEMO"])
    parser.add_argument("--browser-executable", default="")
    args = parser.parse_args()
    candidates = [Path(args.browser_executable)] if args.browser_executable else [
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe")]
    executable = next((str(path) for path in candidates if path.is_file()), None)
    output = ROOT / "output/screenshots"
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(**({"executable_path": executable} if executable else {}), headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        browser_errors = []
        page.on("pageerror", lambda error: browser_errors.append(str(error)))

        def settled():
            page.get_by_text("Snowflake/Cortex migration pending", exact=False).wait_for(timeout=30000)
            expect(page.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning", timeout=30000)
            # An explicit rerun can briefly leave the prior widget tree on screen.
            # Wait for its removal before interacting with the current screen.
            expect(page.get_by_role("tablist")).to_have_count(1, timeout=30000)
            assert page.locator('[data-testid="stException"]').count() == 0

        def select(label, pattern):
            page.get_by_role("combobox", name=label, exact=True).click()
            page.get_by_role("option", name=re.compile(pattern)).click()
            settled()

        def screenshot(name):
            settled()
            page.screenshot(path=str(output / name), full_page=True)

        page.goto("http://127.0.0.1:8501", wait_until="domcontentloaded")
        settled()
        expect(page.get_by_text("Ananya Iyer", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Generate next best action", exact=True)).to_be_visible()
        screenshot("customer-360-desktop.png")
        checks.append("Customer 360 renders borrower facts, evidence and current recommendation")

        page.get_by_role("tab", name="Approvals & execution", exact=True).click()
        select("Action to review", "Ananya")
        expect(page.get_by_role("button", name="Approve action", exact=True)).to_be_disabled()
        screenshot("approvals-desktop.png")
        select("Demo operator", "Arjun")
        expect(page.get_by_role("button", name="Approve action", exact=True)).to_be_enabled()
        page.get_by_role("button", name="Approve action", exact=True).click()
        page.get_by_text("Approved by arjun", exact=True).wait_for(timeout=30000)
        checks.append("Analyst approval disabled; manager approval succeeds")

        page.get_by_role("tab", name="Voice lab", exact=True).click()
        page.get_by_role("button", name="Start local voice session", exact=True).click()
        page.get_by_text("Await Permission", exact=True).wait_for(timeout=30000)
        settled()
        assert page.locator("audio").count() >= 1
        screenshot("voice-permission-desktop.png")

        def turn(text, expected):
            expect(page.get_by_role("textbox", name="Synthetic borrower response", exact=True)).to_have_count(1, timeout=30000)
            page.get_by_role("textbox", name="Synthetic borrower response", exact=True).fill(text)
            page.get_by_role("button", name="Send borrower response", exact=True).click()
            page.get_by_text(expected, exact=True).wait_for(timeout=30000)
            settled()

        turn("Yes, you may continue", "Await Identity")
        turn("Yes, I am the account holder", "Active")
        screenshot("voice-active-desktop.png")
        turn("I am interested", "Ended")
        assert "Outcome: Accept" in page.locator("body").inner_text()
        screenshot("voice-ended-desktop.png")
        checks.append("Voice permission and demo identity gates, actual lender audio, interest outcome and transcript")

        page.get_by_role("tab", name="Action history", exact=True).click()
        settled()
        link = page.get_by_role("link", name="Open demo offer", exact=True)
        expect(link).to_be_visible()
        offer = context.new_page()
        offer.goto(link.get_attribute("href"), wait_until="domcontentloaded")
        expect(offer.get_by_role("heading", name="Your conditional invitation", exact=True)).to_be_visible()
        assert "Ananya" in offer.locator("body").inner_text()
        offer.screenshot(path=str(output / "offer-desktop.png"), full_page=True)
        offer.get_by_role("button", name="Request a callback", exact=True).click()
        expect(offer.get_by_text("Your callback request has been recorded", exact=False)).to_be_visible()
        checks.append("Created invitation renders and public callback form records outcome")
        offer.close()

        page.get_by_role("tab", name="Ask Samvaad", exact=True).click()
        page.get_by_role("button", name="Ask selected question", exact=True).click()
        page.get_by_text("Supporting evidence", exact=False).wait_for(timeout=30000)
        screenshot("ask-desktop.png")
        checks.append("Customer-scoped assistant answer and evidence render")
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("tab", name="Customer 360", exact=True).click()
        screenshot("customer-360-mobile.png")
        overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        assert not overflow, "Mobile viewport has horizontal overflow"
        checks.append("390px viewport renders without document horizontal overflow")
        assert not browser_errors, "Browser JavaScript raised an error"
        context.close()
        browser.close()
    report = {"passed": len(checks), "checks": checks, "browser": "fresh isolated headless Chromium context; installed browser executable", "user_profile_accessed": False, "real_calls_placed": False, "screenshots": str(output), "layout_review": "Inspect saved PNG files separately"}
    (ROOT / "output/local-browser-check.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
