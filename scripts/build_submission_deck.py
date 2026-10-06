"""Build editable PPTX with artifact-tool, then a visually matching 16:9 PDF.

PDF dependencies are intentionally isolated under .local/submission-tools.
The repository application requirements are not modified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "output" / "submission-deck-build"
QA = ROOT / "output" / "submission-deck-qa"
SUBMISSION = ROOT / "submission"
sys.path.insert(0, str(ROOT / ".local" / "submission-tools"))


def build() -> None:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for @oai/artifact-tool.")
    skill = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".codex/plugins/cache/openai-primary-runtime/presentations/26.805.11740/skills/presentations"
    helper = skill / "container_tools/setup_artifact_tool_workspace.mjs"
    BUILD.mkdir(parents=True, exist_ok=True)
    if not (BUILD / "node_modules/@oai/artifact-tool").exists():
        subprocess.run([node, str(helper), "--workspace", str(BUILD)], check=True, cwd=Path.home())
    copied = BUILD / "build_submission_deck.mjs"
    shutil.copyfile(ROOT / "scripts/build_submission_deck.mjs", copied)
    from PIL import Image
    crop_specs = {
        "command-center-desktop.png": (.215, .04, .01, .025),
        "customer360-desktop.png": (.22, .175, .02, .2),
        "call-outcome-desktop.png": (.22, .292, .3, .224),
        "customer-hub-source-sync.png": (.23, .17, .015, .22),
        "usage-protection.png": (.225, .28, .015, .11),
    }
    crop_dir = QA / "screenshots"
    crop_dir.mkdir(parents=True, exist_ok=True)
    for name, (left, top, right, bottom) in crop_specs.items():
        with Image.open(ROOT / "output/cloud/public-browser/hosted" / name) as source:
            width, height = source.size
            source.crop((round(left * width), round(top * height), round((1 - right) * width), round((1 - bottom) * height))).save(crop_dir / name)
    subprocess.run([node, str(copied), str(ROOT)], check=True, cwd=BUILD)
    inspect_dump = SUBMISSION / "Samvaad360_Prototype_Deck.pptx.inspect.ndjson"
    if inspect_dump.exists():
        shutil.move(str(inspect_dump), str(QA / inspect_dump.name))

    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import fitz
    from pypdf import PdfReader

    pdf_path = SUBMISSION / "Samvaad360_Prototype_Deck.pdf"
    pdf = canvas.Canvas(str(pdf_path), pagesize=(960, 540), pageCompression=1)
    pdf.setTitle("Samvaad360 — Customer 360 and Next Best Action Engine")
    pdf.setAuthor("Samvaad360")
    pdf.setSubject("Verified fictional lending prototype — 6 October 2026")
    for n in range(1, 11):
        png = QA / f"slide-{n:02}.png"
        pdf.drawImage(ImageReader(str(png)), 0, 0, width=960, height=540)
        if n == 10:
            pdf.linkURL("https://samvaad360.streamlit.app/", (48, 277.5, 899, 332.25), relative=0, thickness=0)
            pdf.linkURL("https://github.com/Cherie05/samvaad360", (48, 161.25, 899, 210), relative=0, thickness=0)
        pdf.showPage()
    pdf.save()
    doc = fitz.open(pdf_path)
    for n, page in enumerate(doc, 1):
        page.get_pixmap(matrix=fitz.Matrix(1.333, 1.333)).save(str(QA / f"pdf-page-{n:02}.png"))
    pages = len(PdfReader(pdf_path).pages)
    assert pages == 10
    assert pdf_path.stat().st_size < 5 * 1024 * 1024
    off_canvas = []
    wrapped_titles = []
    element_count = 0
    for layout_file in sorted(QA.glob("slide-*.layout.json")):
        layout = json.loads(layout_file.read_text(encoding="utf-8"))
        for element in layout["elements"]:
            element_count += 1
            x, y, width, height = element["bbox"]
            if min(x, y) < 0 or x + width > 1280.01 or y + height > 720.01:
                off_canvas.append({"slide": layout["slide"]["slide"], "name": element.get("name")})
            if re.fullmatch(r"s\d+-title", element.get("name", "")) and element.get("textLayout", {}).get("lineCount", 0) > 1:
                wrapped_titles.append({"slide": layout["slide"]["slide"], "name": element.get("name")})
    assert not off_canvas and not wrapped_titles, (off_canvas, wrapped_titles)
    pptx_path = SUBMISSION / "Samvaad360_Prototype_Deck.pptx"
    with ZipFile(pptx_path) as package:
        xml_names = [name for name in package.namelist() if name.endswith((".xml", ".rels"))]
        xml = "\n".join(package.read(name).decode("utf-8") for name in xml_names)
        secret_patterns = [
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            r"gh[pousr]_[A-Za-z0-9_]{20,}",
            r"github_pat_[A-Za-z0-9_]{20,}",
            r"(?:password|access_token|api_key|private_key)\s*[=:]\s*[\"']?[^\s<\"']{12,}",
        ]
        matches = [pattern for pattern in secret_patterns if re.search(pattern, xml, re.IGNORECASE)]
        assert not matches, "Credential pattern detected in PPTX XML; inspect privately."
        notes_count = sum(bool(re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name)) for name in package.namelist())
        assert notes_count == 10
        assert xml.count("[Sources]") == 10
    final_links = [annotation.get_object().get("/A", {}).get("/URI") for annotation in PdfReader(pdf_path).pages[-1].get("/Annots", [])]
    assert final_links == ["https://samvaad360.streamlit.app/", "https://github.com/Cherie05/samvaad360"]
    images = [Image.open(QA / f"slide-{n:02}.png").convert("RGB") for n in range(1, 11)]
    thumbnails = []
    for image in images:
        image.thumbnail((384, 216))
        thumbnails.append(image)
    sheet = Image.new("RGB", (384 * 2 + 30, 216 * 5 + 60), "#E7EDE8")
    for i, thumb in enumerate(thumbnails):
        sheet.paste(thumb, (10 + i % 2 * 394, 10 + i // 2 * 226))
    sheet.save(QA / "contact-sheet.png")
    result = {
        "pptx": str(SUBMISSION / "Samvaad360_Prototype_Deck.pptx"),
        "pdf": str(pdf_path), "pages": pages,
        "pptx_bytes": (SUBMISSION / "Samvaad360_Prototype_Deck.pptx").stat().st_size,
        "pdf_bytes": pdf_path.stat().st_size,
        "pdf_under_5mb": True,
        "rendered_slide_count": 10, "rendered_pdf_page_count": 10,
        "layout_elements_checked": element_count,
        "off_canvas_elements": off_canvas, "wrapped_slide_titles": wrapped_titles,
        "pptx_xml_parts_scanned": len(xml_names), "credential_pattern_matches": 0,
        "speaker_notes_count": notes_count, "sources_blocks": 10,
        "pdf_clickable_links": final_links,
        "visual_qa": "Review each full-size slide and PDF render before delivery.",
        "template": "Provisional custom deck; organizer template not supplied.",
    }
    (QA / "build-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    build()
