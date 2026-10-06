"""Publish reviewed submission artifacts using the owner's existing Git login.

No credentials are copied into artifacts or workflow settings. Re-running is
safe when existing assets have the same name/size; differing assets are held
for a deliberate versioned release rather than deleted automatically.
"""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.github_actions import session

ROOT = Path(__file__).resolve().parents[1]
TAG = "hackathon-submission-2026"
FILES = {
    "Samvaad360_Prototype_Deck.pdf": "application/pdf",
    "Samvaad360_Prototype_Deck.pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "Samvaad360_Demo.mp4": "video/mp4",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    assets = []
    for name, mime in FILES.items():
        path = ROOT / "submission" / name
        if not path.is_file() or path.stat().st_size < 1000:
            raise SystemExit("SUBMISSION_ASSET_MISSING_OR_EMPTY")
        if path.suffix == ".pdf" and path.stat().st_size > 5_000_000:
            raise SystemExit("DECK_EXCEEDS_PORTAL_SIZE_LIMIT")
        assets.append({"name": name, "mime": mime, "bytes": path.stat().st_size,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if not args.apply:
        print(json.dumps({"status": "PREVIEW", "tag": TAG, "assets": assets}, indent=2))
        return
    client = session("Cherie05")
    base = "https://api.github.com/repos/Cherie05/samvaad360"
    body = (ROOT / "submission/release-notes.md").read_text(encoding="utf-8")
    response = client.get(base + "/releases/tags/" + TAG, timeout=30)
    if response.status_code == 404:
        response = client.post(base + "/releases", json={"tag_name": TAG,
            "target_commitish": "main", "name": "Samvaad 360 — hackathon prototype and submission materials",
            "body": body, "draft": False, "prerelease": True}, timeout=30)
        response.raise_for_status()
    else:
        response.raise_for_status()
        release_id = response.json()["id"]
        response = client.patch(base + f"/releases/{release_id}", json={"body": body}, timeout=30)
        response.raise_for_status()
    release = response.json()
    present = {item["name"]: item for item in release.get("assets", [])}
    endpoint = release["upload_url"].split("{")[0]
    for asset in assets:
        existing = present.get(asset["name"])
        if existing:
            if existing["size"] != asset["bytes"]:
                raise SystemExit("PUBLISHED_ASSET_DIFFERS_USE_NEW_VERSION")
            digest = existing.get("digest")
            if digest and digest != "sha256:" + asset["sha256"]:
                raise SystemExit("PUBLISHED_ASSET_DIGEST_DIFFERS_USE_NEW_VERSION")
            asset["url"] = existing["browser_download_url"]
            continue
        # Do not reuse shell interpolations for upload content or credentials.
        with (ROOT / "submission" / asset["name"]).open("rb") as stream:
            response = client.post(endpoint, params={"name": asset["name"]}, data=stream,
                                   headers={"Content-Type": asset["mime"]}, timeout=180)
        response.raise_for_status()
        asset["url"] = response.json()["browser_download_url"]
        print("PUBLIC_ASSET_UPLOADED: " + asset["name"], flush=True)
    report = {"status": "PUBLISHED", "release": release["html_url"], "assets": assets,
              "portal_submitted": False, "organizer_template_verified": False,
              "coco_video_requirement_verified": False}
    path = ROOT / "output/submission-release.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
