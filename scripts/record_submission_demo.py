"""Record the actual anonymous website; narrate fictional flows, never place calls.

This product walkthrough does not claim CoCo CLI execution. A separate genuine
CLI segment is required by the organizer before the full video is compliant.
Optional artifact-only packages live in .local/submission-tools, not the app.
"""
import argparse
import io
import json
import re
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".local/submission-tools"))

import imageio_ffmpeg
from playwright.sync_api import expect, sync_playwright
from samvaad.voice_audio import synthesize

CHAPTERS = [
    ("01 / Snowflake-backed customer intelligence", "Welcome to Samvaad 360, a Customer 360 and Next Best Action prototype for lending. This is the actual public website. Twenty fictional customers come from a protected, read-only Snowflake snapshot. The command center combines repayment facts with customer conversations to prioritize support, retention and eligible growth. Everything in this recording uses fictional data."),
    ("02 / Explainable portfolio priorities", "The portfolio charts show outstanding exposure, intervention mix and action priorities. These are calculated from the fictional records rather than invented business outcomes. A shared hourly snapshot keeps ordinary visitor workflows away from warehouse queries. This is application usage protection, not a guarantee of account-wide credit spending or production-scale denial-of-service protection."),
    ("03 / One relationship, structured facts and conversations", "Here is Imran's customer journey. Loans, repayments, policy checks and conversation evidence appear together. The recommendation includes its reasons and required review. A lender can see why an action was proposed instead of relying on an unexplained score. The public website uses the same deterministic decision rules as the tested local application."),
    ("04 / Grounded answers with evidence", "The evidence desk answers a customer-scoped question using the relationship facts and supporting interactions. The provider label is explicit: this response uses a protected Snowflake snapshot and deterministic evidence summary. It does not claim a live language-model request. The application also refuses questions that refer to a different customer, and can export a scoped evidence packet."),
    ("05 / Human review before conversation", "An operator adds the proposal to a review queue and records a fictional approval. That approval unlocks a conversation rehearsal. On this anonymous website, reviews belong only to this browser visit and cannot change financial terms or another visitor's data. The separate private local service persists reviews and enforces the designated reviewer roles."),
    ("06 / Permission and identity gates", "The call studio first asks permission to continue and then confirms the account holder before discussing the proposal. These are rehearsal gates rather than verified production identity checks. Browser speech controls and a readable transcript are available. The telephone provider integration is present but disabled here. No phone call, SMS or financial transaction is being performed."),
    ("07 / New hardship changes the next action", "Now the borrower says, I lost my job. The conversation stops the growth proposal, records the new fictional evidence and records a supportive officer handoff. The before-and-after view shows that the earlier growth action is no longer eligible. This is the central workflow: input, policy processing and an observable outcome, with an officer reviewing the customer's changed situation."),
    ("08 / Reviewed onboarding without an invented loan", "Customer hub completes the relationship workflow. We submit a fictional applicant and approve an officer-reviewed application. The new Customer 360 contains a relationship record, with no invented loan. Public exercises remain within this visit. The private local portal also provides expiring, scoped applicant invitations and stores intake, attestations and manager review transactionally."),
    ("09 / Source imports validate before they commit", "The source-data adapter previews matching customer, loan, payment and conversation records before applying anything. Source identifiers and increasing versions support reconciliation and safe replay; conflicts block the import. We explicitly apply this fictional example within the visit. The private service supports persistent CSV and JSON imports. Continuous lender integration and the private Snowflake publisher still need production configuration."),
    ("10 / Customer control and release evidence", "A customer can request service and withdraw contact permission. That withdrawal blocks further review and conversation in this visit. The release passed 557 automated tests, 20 anonymous hosted-browser checks and six private relationship browser checks. This is a verified hackathon prototype. Production authentication, real carrier delivery and continuous integration remain release gates. The required genuine CoCo CLI recording is a separate submission requirement."),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encode-existing", action="store_true", help="Re-encode a previously captured real walkthrough; no website or model request")
    parser.add_argument("--speed", type=float, default=1.4, help="Clearly recorded walkthrough playback speed, between 1 and 1.5")
    args = parser.parse_args()
    if not 1 <= args.speed <= 1.5:
        raise SystemExit("Choose a playback speed between 1 and 1.5.")
    folder = ROOT / "output/submission-video"
    folder.mkdir(parents=True, exist_ok=True)
    final = ROOT / "submission/Samvaad360_Demo.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    if args.encode_existing:
        proof = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        raw = max(folder.glob("*.webm"), key=lambda path: path.stat().st_mtime)
        encode(raw, folder / "narration.wav", final, args.speed, proof, folder)
        return
    narration = []
    for number, (_, text) in enumerate(CHAPTERS):
        audio = synthesize(text)["audio"]
        with wave.open(io.BytesIO(audio), "rb") as stream:
            narration.append((stream.getparams(), stream.readframes(stream.getnframes())))
        print(f"NARRATION_READY_{number + 1}", flush=True)
    proof = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
             "url": "https://samvaad360.streamlit.app/", "real_call_placed": False,
             "coco_cli_executed_in_this_video": False, "chapters": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                      record_video_dir=str(folder),
                                      record_video_size={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(proof["url"], wait_until="domcontentloaded")
        page.locator("iframe[src*='/~/+/']").wait_for(timeout=60000)
        app = page.frame_locator("iframe[src*='/~/+/']")
        app.get_by_role("tab", name="Command center", exact=True).wait_for(timeout=60000)
        expect(app.get_by_text("Data source: Snowflake", exact=True)).to_be_visible(timeout=30000)
        proof["live_snowflake_backend_verified"] = True
        started = time.monotonic()
        # Video starts when its page is created; retain the actual startup lead-in.
        video = page.video
        # For audio alignment, measure browser recording's startup separately.
        recording_startup = page.evaluate("performance.now() / 1000")
        page.evaluate("""() => {
          const bar = document.createElement('div'); bar.id = 'submission-caption';
          Object.assign(bar.style, {position:'fixed',bottom:'0',left:'0',right:'0',
            zIndex:'2147483647',background:'#163e32',color:'#fffdf4',padding:'12px 22px',
            font:'600 19px Segoe UI, sans-serif',boxShadow:'0 -2px 9px #0003'});
          document.body.appendChild(bar);
        }""")

        def tab(label):
            app.get_by_role("tab", name=label, exact=True).click()
            expect(app.get_by_role("tab", name=label, exact=True)).to_have_attribute("aria-selected", "true")

        def customer(name):
            tab("Customer 360")
            app.get_by_text("Omnichannel journey", exact=True).wait_for(timeout=30000)
            picker = app.get_by_role("combobox", name="Customer", exact=True)
            picker.click()
            picker.fill(name)
            app.get_by_role("option", name=re.compile(re.escape(name))).click()
            app.get_by_role("heading", name=name, exact=True).wait_for(timeout=30000)

        for number, (title, text) in enumerate(CHAPTERS):
            chapter_start = time.monotonic() - started + recording_startup
            page.locator("#submission-caption").evaluate("(element, text) => element.textContent = text", title)
            if number == 0:
                app.get_by_text("20 fictional customer relationships", exact=True).wait_for()
            elif number == 1:
                app.get_by_text("Portfolio intelligence", exact=True).scroll_into_view_if_needed()
                expect(app.locator('[data-testid="stVegaLiteChart"]')).to_have_count(3, timeout=20000)
            elif number == 2:
                customer("Imran Shaikh")
                app.get_by_text("Omnichannel journey", exact=True).scroll_into_view_if_needed()
            elif number == 3:
                tab("Evidence desk")
                app.get_by_role("textbox", name="Question", exact=True).fill("Why is this next action recommended?")
                app.get_by_role("button", name="Find the evidence", exact=True).click()
                app.get_by_text("Protected Snowflake snapshot + deterministic evidence summary", exact=True).wait_for(timeout=30000)
            elif number == 4:
                customer("Imran Shaikh")
                app.get_by_role("button", name="Add to review queue", exact=True).click()
                app.get_by_role("textbox", name="Review note", exact=True).fill("Fictional submission walkthrough: evidence and policy reviewed")
                app.get_by_role("button", name="Save review decision", exact=True).click()
                app.get_by_text("Review note: Fictional submission walkthrough: evidence and policy reviewed", exact=True).wait_for(timeout=30000)
            elif number == 5:
                app.get_by_role("button", name=re.compile("^Open call studio")).click()
                expect(app.get_by_role("button", name="Place telephone call", exact=True)).to_be_disabled()
                app.get_by_role("button", name="Start conversation rehearsal", exact=True).click()
                app.get_by_role("button", name="Yes, you may continue", exact=True).click()
                app.get_by_role("button", name="Yes, I am the account holder", exact=True).click()
                app.get_by_role("textbox", name="Borrower reply", exact=True).wait_for(timeout=30000)
            elif number == 6:
                app.get_by_role("button", name="I lost my job", exact=True).click()
                app.get_by_text("Recorded outcome: Human handoff", exact=True).wait_for(timeout=30000)
                app.locator(".compare-card").scroll_into_view_if_needed()
            elif number == 7:
                tab("Customer hub")
                app.get_by_role("textbox", name="Fictional customer name", exact=True).fill("Submission Demo Applicant")
                app.get_by_text("Identity review attested by an officer", exact=True).click()
                app.get_by_text("Document review attested by an officer", exact=True).click()
                app.get_by_role("button", name="Submit fictional application", exact=True).click()
                app.get_by_role("button", name="Save fictional review", exact=True).wait_for(timeout=30000)
                app.get_by_role("button", name="Save fictional review", exact=True).click()
                customer("Submission Demo Applicant")
                app.get_by_text("0 active loan(s)", exact=True).wait_for(timeout=30000)
            elif number == 8:
                tab("Customer hub")
                app.get_by_text("Data sync", exact=True).click()
                app.get_by_role("button", name="Preview sample import", exact=True).click()
                expect(app.get_by_text("Import status:", exact=False)).to_contain_text("VALIDATED", timeout=30000)
                expect(app.get_by_role("button", name="Apply rehearsal import", exact=True)).to_be_disabled()
                app.get_by_text("Apply these fictional records to this visit only", exact=True).click()
                app.get_by_role("button", name="Apply rehearsal import", exact=True).click()
                expect(app.get_by_text("Import status:", exact=False)).to_contain_text("COMMITTED", timeout=30000)
            else:
                app.get_by_text("Customer portal", exact=True).click()
                picker = app.get_by_role("combobox", name="Preview as fictional customer", exact=True)
                picker.click()
                picker.fill("Ananya")
                option = app.get_by_role("option", name=re.compile(r"^Ananya\b"))
                name = option.inner_text().strip()
                option.click()
                app.get_by_role("button", name="Submit self-service request", exact=True).click()
                app.get_by_role("button", name="Rehearse withdrawing all contact permission", exact=True).click()
                customer(name)
                expect(app.get_by_role("button", name="Add to review queue", exact=True)).to_be_disabled()
                app.get_by_text("Calls not permitted", exact=True).wait_for()
            parameters, frames = narration[number]
            audio_seconds = len(frames) / parameters.sampwidth / parameters.nchannels / parameters.framerate
            elapsed = time.monotonic() - started + recording_startup - chapter_start
            page.wait_for_timeout(max(2500, (max(25, audio_seconds + 3) - elapsed) * 1000))
            proof["chapters"].append({"title": title, "start": round(chapter_start, 3),
                                      "end": round(time.monotonic() - started + recording_startup, 3),
                                      "narration": text})
            page.screenshot(path=str(folder / f"chapter-{number + 1:02d}.png"))
            print(f"LIVE_CHAPTER_VERIFIED_{number + 1}", flush=True)
        context.close()
        raw = Path(video.path())
        browser.close()
    parameters = narration[0][0]
    assert all(p.nchannels == parameters.nchannels and p.sampwidth == parameters.sampwidth and
               p.framerate == parameters.framerate for p, _ in narration)
    bytes_per_second = parameters.nchannels * parameters.sampwidth * parameters.framerate
    sound = bytearray(int((proof["chapters"][-1]["end"] + 3) * bytes_per_second))
    for chapter, (_, frames) in zip(proof["chapters"], narration):
        offset = int(chapter["start"] * parameters.framerate) * parameters.sampwidth * parameters.nchannels
        sound[offset:offset + len(frames)] = frames
    wav = folder / "narration.wav"
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(parameters.nchannels)
        out.setsampwidth(parameters.sampwidth)
        out.setframerate(parameters.framerate)
        out.writeframes(sound)
    proof.update(status="PASSED", recorded_duration_seconds=proof["chapters"][-1]["end"],
                 media=str(final.relative_to(ROOT)), full_coco_video_requirement_satisfied=False,
                 narration_provider="Windows installed SAPI voice; application walkthrough narration")
    encode(raw, wav, final, args.speed, proof, folder)


def encode(raw, wav, final, speed, proof, folder):
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(raw), "-i", str(wav),
                    "-filter:v", f"setpts=PTS/{speed}", "-filter:a", f"atempo={speed}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "25", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-shortest", str(final)],
                   capture_output=True, check=True, timeout=240)
    check = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(final)], capture_output=True, text=True, timeout=15)
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", check.stderr)
    if not match:
        raise SystemExit("Encoded video duration could not be verified.")
    hours, minutes, seconds = map(float, match.groups())
    duration = hours * 3600 + minutes * 60 + seconds
    if not 180 <= duration <= 300:
        raise SystemExit("The final product walkthrough must be between 3 and 5 minutes.")
    proof.update(duration_seconds=duration, recorded_duration_seconds=proof["chapters"][-1]["end"],
                 video_bytes=final.stat().st_size, playback_speed=speed, duration_requirement_satisfied=True)
    (folder / "result.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in proof.items() if k != "chapters"}, indent=2))


if __name__ == "__main__":
    main()
