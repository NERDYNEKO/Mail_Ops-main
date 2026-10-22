"""Make a per recipient copy of the proposal with the event name on the cover."""
import html
import os
import shutil
import subprocess
import tempfile

import pymupdf

BASE = "assets/Mapster_Pilot_Proposal_base.pdf"
OLD = "International Mining"
FONT = "helv"


def _find_line(page):
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            if OLD in "".join(s["text"] for s in ln["spans"]):
                return pymupdf.Rect(ln["bbox"])
    raise RuntimeError("Cover line not found in base PDF")


def _overlay(event_name: str, out_path: str) -> str:
    doc = pymupdf.open(BASE)
    page = doc[0]
    bbox = _find_line(page)
    # sample the background left of the text so the patch blends in
    pix = page.get_pixmap(clip=pymupdf.Rect(bbox.x0 - 25, bbox.y0 + 2, bbox.x0 - 15, bbox.y1 - 2))
    r, g, b = pix.pixel(2, 2)
    page.add_redact_annot(pymupdf.Rect(bbox.x0 - 2, bbox.y0 - 1, bbox.x1 + 12, bbox.y1 + 1),
                          fill=(r / 255, g / 255, b / 255))
    page.apply_redactions()
    size = 11.0
    while pymupdf.get_text_length(event_name, FONT, size) > 420 and size > 7:
        size -= 0.5
    w = pymupdf.get_text_length(event_name, FONT, size)
    x = bbox.x0
    page.insert_text((x, bbox.y1 - 3.5), event_name, fontname=FONT, fontsize=size,
                     color=(0.078, 0.078, 0.169))
    doc.save(out_path)
    return out_path


TEMPLATE = os.path.join("assets", "proposal.html")
EDGES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
         r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def _browser():
    return next((e for e in EDGES if os.path.exists(e)), shutil.which("msedge") or shutil.which("chrome"))


def make_proposal(event_name: str, out_path: str) -> str:
    """Render the proposal from the HTML template with the recipient name on the cover."""
    exe = _browser()
    if not exe or not os.path.exists(TEMPLATE):
        return _overlay(event_name, out_path)
    src = open(TEMPLATE, encoding="utf-8").read().replace("{{NAME}}", html.escape(event_name))
    tmp = tempfile.mkdtemp(prefix="mapster_pdf_")
    try:
        for f in os.listdir("assets"):
            if f.endswith(".png"):
                shutil.copy(os.path.join("assets", f), tmp)
        page = os.path.join(tmp, "p.html")
        open(page, "w", encoding="utf-8").write(src)
        out = os.path.abspath(out_path)
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={os.path.join(tmp, 'profile')}",
                        f"--print-to-pdf={out}", "file:///" + page.replace(os.sep, "/")],
                       capture_output=True, timeout=90)
        if not os.path.exists(out) or os.path.getsize(out) < 5000:
            return _overlay(event_name, out_path)
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import sys
    print(make_proposal(sys.argv[1], sys.argv[2]))
