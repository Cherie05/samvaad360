"""Check the localhost public UI against real restricted Snowflake reads.

Uses a fresh standalone browser because signed-in browser control is unavailable.
No account password, service key or hosting browser session is accessed here.
"""
import argparse
import json
import re
from datetime import datetime, timezone

from playwright.sync_api import expect, sync_playwright
from cloud.config import WORKSPACE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8502")
    args = parser.parse_args()
    if not (args.url == "http://127.0.0.1:8502" or
            re.fullmatch(r"https://[a-z0-9-]+\.streamlit\.app/?", args.url)):
        raise SystemExit("Use the local preview or the deployed Streamlit app URL.")
    hosted = args.url.startswith("https://")
    folder = WORKSPACE / "output/cloud/public-browser"
    folder.mkdir(parents=True, exist_ok=True)
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "url": args.url,
              "scope": "anonymous hosted app" if hosted else "localhost public app with real Snowflake reader",
              "public_host_verified": False, "financial_execution": False, "checks": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        page.get_by_text("Data source: Snowflake", exact=True).wait_for(timeout=60000)
        page.get_by_role("tab", name="Customer 360", exact=True).wait_for(timeout=60000)
        expect(page.get_by_role("tab")).to_have_count(4, timeout=30000)
        report["checks"].append("four tabs and real Snowflake source")

        def select_customer(name):
            page.get_by_role("tab", name="Customer 360", exact=True).click()
            page.get_by_role("combobox", name="Customer", exact=True).click()
            page.get_by_role("option", name=re.compile(name)).click()
            page.get_by_role("heading", name=name, exact=True).wait_for(timeout=30000)

        select_customer("Imran Shaikh")
        page.get_by_role("button", name="Try review workflow", exact=True).click()
        page.get_by_text("Recommendation added to your simulation.", exact=False).wait_for()
        page.screenshot(path=str(folder / "customer360-desktop.png"), full_page=True)
        page.get_by_role("tab", name="Review simulation", exact=True).click()
        page.get_by_text(re.compile("C0003.*PENDING_SIMULATION")).click()
        page.get_by_role("textbox", name="Fictional review note", exact=True).fill("Public Snowflake UI check")
        page.get_by_role("button", name="Save simulation decision", exact=True).click()
        page.get_by_text(re.compile("C0003.*APPROVED_IN_SIMULATION")).wait_for(timeout=30000)
        page.get_by_text(re.compile("C0003.*APPROVED_IN_SIMULATION")).click()
        page.get_by_text("Simulation note: Public Snowflake UI check", exact=True).wait_for()
        page.wait_for_timeout(300)
        page.screenshot(path=str(folder / "review-desktop.png"), full_page=True)
        report["checks"].append("top-up review simulation and saved session note")

        second = browser.new_context(viewport={"width": 1200, "height": 900})
        second_page = second.new_page()
        second_page.goto(args.url, wait_until="domcontentloaded")
        second_page.get_by_role("tab", name="Review simulation", exact=True).wait_for(timeout=30000)
        second_page.get_by_role("tab", name="Review simulation", exact=True).click()
        second_page.get_by_text("Choose a customer and click Try review workflow", exact=False).wait_for()
        assert "APPROVED_IN_SIMULATION" not in second_page.locator("body").inner_text()
        report["checks"].append("another visitor cannot see the first review simulation")

        page.get_by_role("tab", name="Ask with evidence", exact=True).click()
        page.get_by_role("textbox", name="Question", exact=True).fill("Summarize C0002")
        page.get_by_role("button", name="Ask", exact=True).click()
        page.get_by_text("That question refers to another customer.", exact=False).wait_for(timeout=30000)
        page.get_by_role("textbox", name="Question", exact=True).fill("Why is this next action recommended?")
        page.get_by_role("button", name="Ask", exact=True).click()
        page.get_by_text("Snowflake data + deterministic evidence summary", exact=True).wait_for(timeout=30000)
        report["checks"].append("scoped evidence answer and cross-customer refusal")

        select_customer("Neha Rao")
        page.get_by_role("tab", name="Customer 360", exact=True).click()
        assert page.get_by_role("button", name="Try review workflow", exact=True).is_disabled()
        report["checks"].append("DND profile cannot enter a review simulation")

        mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile_page = mobile.new_page()
        mobile_page.goto(args.url, wait_until="domcontentloaded")
        mobile_page.get_by_role("heading", name="Ravi Kumar", exact=True).wait_for(timeout=30000)
        assert mobile_page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        mobile_page.screenshot(path=str(folder / "customer360-mobile.png"), full_page=True)
        report["checks"].append("mobile layout without page overflow")
        browser.close()
    report.update(status="PASSED", public_host_verified=hosted, passed=len(report["checks"]),
                  screenshots=["customer360-desktop.png", "review-desktop.png", "customer360-mobile.png"])
    (folder / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
