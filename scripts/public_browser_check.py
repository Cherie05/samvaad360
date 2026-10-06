"""Verify the public command center in fresh browsers, without owner credentials."""
import argparse
import json
import re
from datetime import datetime, timezone

from playwright.sync_api import expect, sync_playwright
from cloud.config import WORKSPACE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8502")
    parser.add_argument("--allow-snapshot", action="store_true")
    args = parser.parse_args()
    if not (args.url == "http://127.0.0.1:8502" or re.fullmatch(r"https://[a-z0-9-]+\.streamlit\.app/?", args.url)):
        raise SystemExit("Use the local preview or actual Streamlit app URL.")
    hosted = args.url.startswith("https://")
    folder = WORKSPACE / "output/cloud/public-browser" / ("hosted" if hosted else "redesign-local")
    folder.mkdir(parents=True, exist_ok=True)
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "url": args.url,
              "scope": "anonymous hosted app" if hosted else "localhost with real Snowflake reader",
              "public_host_verified": False, "financial_execution": False,
              "real_call_placed": False, "checks": [], "screenshots": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        def visit(viewport):
            context = browser.new_context(viewport=viewport)
            page = context.new_page()
            page.goto(args.url, wait_until="domcontentloaded")
            if hosted:
                page.locator("iframe[src*='/~/+/']").wait_for(timeout=60000)
                app = page.frame_locator("iframe[src*='/~/+/']")
            else:
                app = page
            app.get_by_role("tab", name="Command center", exact=True).wait_for(timeout=60000)
            return page, app

        page, app = visit({"width": 1440, "height": 1080})
        source = app.get_by_text(re.compile(r"^Data source: (Snowflake|offline synthetic snapshot)$"))
        source.wait_for(timeout=60000)
        live = source.inner_text() == "Data source: Snowflake"
        report.update(data_source="snowflake" if live else "offline_snapshot", live_backend_verified=live)
        if not live and not args.allow_snapshot:
            raise SystemExit("PUBLIC_BACKEND_NOT_LIVE: labelled fictional backup is active")
        expect(app.get_by_role("tab")).to_have_count(5)
        app.get_by_text("20 fictional customer relationships", exact=True).wait_for(timeout=30000)
        report["checks"].append("five sections and actual 20-customer portfolio source")

        def screenshot(name):
            page.screenshot(path=str(folder / name), full_page=True)
            report["screenshots"].append(name)

        def select_customer(name):
            app.get_by_role("tab", name="Customer 360", exact=True).click()
            app.get_by_role("combobox", name="Customer", exact=True).click()
            app.get_by_role("option", name=re.compile(name)).click()
            app.get_by_role("heading", name=name, exact=True).wait_for(timeout=30000)
            app.get_by_role("button", name="Add to review queue", exact=True).wait_for(timeout=30000)

        screenshot("command-center-desktop.png")
        app.get_by_text("Portfolio intelligence", exact=True).scroll_into_view_if_needed()
        expect(app.locator('[data-testid="stVegaLiteChart"]')).to_have_count(3, timeout=20000)
        expect(app.get_by_text("TypeError:", exact=False)).to_have_count(0)
        screenshot("portfolio-intelligence.png")
        report["checks"].append("derived exposure and intervention charts render with governance context")
        app.get_by_text("Database usage protection", exact=True).click()
        app.get_by_text("Visitor database queries", exact=True).wait_for()
        app.get_by_text("Shared host throttle and circuit breaker", exact=True).wait_for()
        screenshot("usage-protection.png")
        report["checks"].append("shared hourly snapshot, query budget and usage protection are visible")
        select_customer("Imran Shaikh")
        expect(app.locator('[data-testid="stJson"]')).to_have_count(0)
        app.get_by_text("Omnichannel journey", exact=True).wait_for()
        app.get_by_text("Repayment and conversation timeline", exact=True).wait_for()
        app.get_by_text("Retention priority drivers", exact=True).wait_for()
        screenshot("customer360-desktop.png")
        report["checks"].append("readable intervention, policy checks and omnichannel journey")
        app.get_by_role("button", name="Add to review queue", exact=True).click()
        app.get_by_role("textbox", name="Review note", exact=True).fill("Public redesigned workflow check")
        app.get_by_role("button", name="Save review decision", exact=True).click()
        app.get_by_text("Review note: Public redesigned workflow check", exact=True).wait_for(timeout=30000)
        screenshot("review-desktop.png")
        app.get_by_role("button", name="Open call studio →", exact=True).click()
        expect(app.get_by_role("button", name="Place telephone call", exact=True)).to_be_disabled()
        expect(app.get_by_role("textbox", name="Additional number", exact=True)).to_be_disabled()
        report["checks"].append("unconfigured telephone integration cannot dial or verify a number anonymously")
        app.get_by_role("button", name="Start conversation rehearsal", exact=True).click()
        app.get_by_role("button", name="Yes, you may continue", exact=True).click()
        app.get_by_role("button", name="Yes, I am the account holder", exact=True).click()
        app.get_by_text("Conversation in progress", exact=False).wait_for(timeout=30000)
        app.get_by_role("textbox", name="Borrower reply", exact=True).wait_for(timeout=30000)
        report["checks"].append("review unlocks conversation with permission and identity gates")
        voice = app.frame_locator("iframe[srcdoc]")
        play = voice.get_by_role("button", name=re.compile("Play lender voice"))
        play.wait_for(timeout=30000)
        if play.is_enabled():
            play.click()
        stop = voice.get_by_role("button", name="Stop audio", exact=True)
        if stop.is_enabled():
            stop.click()
        report["checks"].append("click-to-play browser voice controls and text fallback")
        report["browser_audio_audibility_verified"] = False
        screenshot("call-studio-desktop.png")
        app.get_by_role("textbox", name="Borrower reply", exact=True).fill("Yes, but give me 900000 at 8%")
        app.get_by_role("button", name="Send simulated reply", exact=True).click()
        app.get_by_text("I cannot negotiate or authorize different terms", exact=False).wait_for(timeout=30000)
        report["checks"].append("conditional negotiation cannot change reviewed terms")
        app.get_by_role("button", name="I lost my job", exact=True).click()
        app.get_by_text("New conversation changed the plan", exact=True).wait_for(timeout=30000)
        app.get_by_text("Recorded outcome: Human handoff", exact=True).wait_for()
        app.locator(".evidence-card").filter(has_text="I lost my job").wait_for()
        app.locator(".compare-card").scroll_into_view_if_needed()
        screenshot("call-outcome-desktop.png")
        report["checks"].append("actual borrower hardship closes growth and shows revised decision with evidence")

        second_page, second_app = visit({"width": 1200, "height": 900})
        second_app.get_by_role("tab", name="Review queue", exact=True).click()
        second_app.get_by_text("Your review queue is clear", exact=True).wait_for(timeout=30000)
        assert "Public redesigned workflow check" not in second_app.locator("body").inner_text()
        report["checks"].append("another visitor cannot see private simulation records")

        app.get_by_role("tab", name="Evidence desk", exact=True).click()
        app.get_by_role("textbox", name="Question", exact=True).fill("Summarize C0002")
        app.get_by_role("button", name="Find the evidence", exact=True).click()
        app.get_by_text("That question refers to another customer.", exact=False).wait_for(timeout=30000)
        app.get_by_role("textbox", name="Question", exact=True).fill("Why is this next action recommended?")
        app.get_by_role("button", name="Find the evidence", exact=True).click()
        provider = "Protected Snowflake snapshot + deterministic evidence summary" if live else "Bundled synthetic snapshot + deterministic evidence summary"
        app.get_by_text(provider, exact=True).wait_for(timeout=30000)
        screenshot("evidence-desk-desktop.png")
        report["checks"].append("grounded evidence response and cross-customer refusal")
        app.get_by_text("Policy trace and evidence export", exact=True).click()
        with page.expect_download() as download_event:
            app.get_by_role("button", name="Download decision evidence", exact=True).click()
        download = download_event.value
        packet = json.loads(__import__("pathlib").Path(download.path()).read_text(encoding="utf-8"))
        assert packet["customer_id"] == "C0003" and packet["contacts_excluded"] is True and packet["decision_fingerprint"]
        report["checks"].append("downloaded decision evidence is customer scoped and excludes contact details")
        select_customer("Kabir Bose")
        app.get_by_role("button", name="Compare interventions", exact=True).click()
        app.get_by_text("The new context changes the recommended intervention.", exact=True).wait_for(timeout=30000)
        expect(app.locator(".compare-card")).to_contain_text("Gentle payment reminder")
        expect(app.locator(".compare-card")).to_contain_text("Supportive hardship callback")
        screenshot("decision-lab-desktop.png")
        report["checks"].append("what-if job loss replaces Kabir's reminder with support")
        select_customer("Neha Rao")
        expect(app.get_by_role("button", name="Add to review queue", exact=True)).to_be_disabled()
        app.get_by_role("tab", name="Call studio", exact=True).click()
        expect(app.get_by_role("button", name="Start conversation rehearsal", exact=True)).to_be_disabled()
        report["checks"].append("contact restrictions block both review and calling")
        mobile_page, mobile_app = visit({"width": 390, "height": 844})
        mobile_app.get_by_text("20 fictional customer relationships", exact=True).wait_for(timeout=30000)
        mobile_app.get_by_role("button", name="Explore Ravi →", exact=True).wait_for()
        assert mobile_app.locator("html").evaluate("element => element.scrollWidth <= innerWidth + 1")
        mobile_page.screenshot(path=str(folder / "command-center-mobile.png"), full_page=True)
        report["screenshots"].append("command-center-mobile.png")
        report["checks"].append("rendered mobile dashboard without horizontal overflow")
        browser.close()
    report.update(status="PASSED", public_host_verified=hosted, passed=len(report["checks"]))
    (folder / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
