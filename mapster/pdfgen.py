"""Per recipient copy of the proposal with the event name on the cover.
Renders assets/proposal.html through headless Edge/Chrome, falling back to patching the base PDF."""
import html
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

from .config import cfg

log = logging.getLogger("mapster")
BASE = cfg.assets_dir / "Mapster_Pilot_Proposal_base.pdf"
TEMPLATE = cfg.assets_dir / "proposal.html"
OLD_TEXT = "International Mining"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def _browser() -> str | None:
    return next((b for b in BROWSERS if Path(b).exists()), shutil.which("msedge") or shutil.which("chrome"))


def _overlay(name: str, out: Path) -> Path:
    doc = pymupdf.open(BASE)
    page = doc[0]
    bbox = next((pymupdf.Rect(ln["bbox"]) for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
                 if OLD_TEXT in "".join(s["text"] for s in ln["spans"])), None)
    if bbox is None:
        raise RuntimeError("Cover line not found in base PDF")
    # sample the background left of the text so the patch blends in
    pix = page.get_pixmap(clip=pymupdf.Rect(bbox.x0 - 25, bbox.y0 + 2, bbox.x0 - 15, bbox.y1 - 2))
    r, g, b = pix.pixel(2, 2)
    page.add_redact_annot(pymupdf.Rect(bbox.x0 - 2, bbox.y0 - 1, bbox.x1 + 12, bbox.y1 + 1),
                          fill=(r / 255, g / 255, b / 255))
    page.apply_redactions()
    size = 11.0
    while pymupdf.get_text_length(name, "helv", size) > 420 and size > 7:
        size -= 0.5
    page.insert_text((bbox.x0, bbox.y1 - 3.5), name, fontname="helv", fontsize=size, color=(0.078, 0.078, 0.169))
    doc.save(out)
    return out


def make_proposal(name: str, out: Path) -> Path:
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    exe = _browser()
    if not exe or not TEMPLATE.exists():
        return _overlay(name, out)
    with tempfile.TemporaryDirectory(prefix="mapster_pdf_") as tmp:
        tmp = Path(tmp)
        for png in cfg.assets_dir.glob("*.png"):
            shutil.copy(png, tmp)
        page = tmp / "p.html"
        page.write_text(TEMPLATE.read_text(encoding="utf-8").replace("{{NAME}}", html.escape(name)), encoding="utf-8")
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={tmp / 'profile'}", f"--print-to-pdf={out}", page.as_uri()],
                       capture_output=True, timeout=90)
        if not out.exists() or out.stat().st_size < 5000:
            log.warning("Browser PDF failed, using overlay fallback")
            return _overlay(name, out)
    return out
