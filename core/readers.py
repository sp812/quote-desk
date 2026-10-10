"""Turn whatever a vendor sent into 'evidence': text with stable locators the AI must cite,
plus the original images/PDFs so the model can see what a human sees.

Locator conventions (the extraction agent is told to cite these exactly):
  email   -> email:L<line>
  xlsx    -> <file>!<Sheet>!<Cell>
  pdf     -> <file>:p<page>:L<line>
  docx    -> <file>:para<n>
  image   -> <file>:<short region description>
"""
from __future__ import annotations
import base64
import io
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Evidence:
    vendor_dir: str
    texts: list[tuple[str, str]] = field(default_factory=list)   # (filename, numbered text)
    images: list[tuple[str, bytes, str]] = field(default_factory=list)  # (filename, bytes, media_type)
    pdfs: list[tuple[str, bytes]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        def cap(b):
            return b if len(b) <= MAX_TEXT_CHARS else b[:MAX_TEXT_CHARS] + "\n[... file truncated: too long to read in full; ask the vendor for the relevant section]"
        return "\n\n".join(f"===== FILE: {name} =====\n{cap(body)}" for name, body in self.texts)


def read_email(p: Path) -> str:
    return "\n".join(f"email:L{i:02d} | {ln}" for i, ln in enumerate(p.read_text(errors="ignore").splitlines(), 1))


def read_xlsx(p: Path) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(p, data_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"--- sheet '{ws.title}' ---")
        for row in ws.iter_rows():
            cells = [f"{c.coordinate}={c.value!r}" for c in row if c.value not in (None, "")]
            if cells:
                out.append(f"{p.name}!{ws.title}!R{row[0].row}: " + " | ".join(cells))
    return "\n".join(out)


def read_pdf(p: Path) -> str:
    import pdfplumber
    out = []
    with pdfplumber.open(p) as pdf:
        for pi, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            for li, ln in enumerate(text.splitlines(), 1):
                out.append(f"{p.name}:p{pi}:L{li} | {ln}")
            # flag small print: words far below the body font size
            sizes = [w.get("size", 0) for w in page.extract_words(extra_attrs=["size"])]
            if sizes:
                body = sorted(sizes)[len(sizes) // 2]
                small = [w for w in page.extract_words(extra_attrs=["size"]) if w.get("size", body) < body * 0.8]
                if small:
                    out.append(f"{p.name}:p{pi} [NOTE: page contains small-print text at ~{small[0]['size']:.1f}pt vs body {body:.1f}pt: "
                               + " ".join(w["text"] for w in small[:60]) + "]")
    return "\n".join(out)


def read_docx(p: Path) -> str:
    import docx
    d = docx.Document(p)
    out = [f"{p.name}:para{i} | {para.text}" for i, para in enumerate(d.paragraphs, 1) if para.text.strip()]
    for ti, t in enumerate(d.tables, 1):
        for ri, row in enumerate(t.rows, 1):
            out.append(f"{p.name}:table{ti}:r{ri} | " + " | ".join(c.text for c in row.cells))
    return "\n".join(out)


def load_vendor(vendor_dir: Path) -> Evidence:
    ev = Evidence(vendor_dir=vendor_dir.name)
    for f in sorted(vendor_dir.iterdir()):
        if f.name.startswith("."):
            continue
        ev.files.append(f.name)
        suf = f.suffix.lower()
        try:
            if f.name == "email.txt" or suf in (".txt", ".eml"):
                ev.texts.insert(0, (f.name, read_email(f)))
            elif suf in (".xlsx", ".xlsm"):
                ev.texts.append((f.name, read_xlsx(f)))
            elif suf == ".pdf":
                ev.texts.append((f.name, read_pdf(f)))
                raw = f.read_bytes()
                if len(raw) <= MAX_PDF_BYTES and _pdf_pages_count(f) <= MAX_PDF_PAGES:
                    ev.pdfs.append((f.name, raw))
                else:   # too big to send as a document; the extracted text (with locators) still goes
                    ev.texts.append((f.name, f"[NOTE: PDF too large to attach as an image ({len(raw) // 1_000_000} MB); read from its text]"))
            elif suf == ".docx":
                ev.texts.append((f.name, read_docx(f)))
            elif suf in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                data, mt = _fit_image(f.read_bytes(), suf)
                ev.images.append((f.name, data, mt))
                ev.texts.append((f.name, "[image attached - read it visually; cite as "
                                 f"{f.name}:<region>, e.g. {f.name}:row '5 Ply Printed']"))
            elif suf == ".csv":
                ev.texts.append((f.name, f.read_text(errors="ignore")))
            else:
                ev.texts.append((f.name, f"[unsupported file type {suf} - not read]"))
        except Exception as e:  # never crash the pipeline on one bad file; surface it instead
            ev.texts.append((f.name, f"[ERROR reading file: {e}]"))
    return ev


MAX_TEXT_CHARS = 180_000      # per file; keeps one huge workbook from overflowing the model's context
MAX_PDF_BYTES = 25_000_000
MAX_PDF_PAGES = 90
MAX_IMAGE_SIDE = 2400         # phone photos are ~4000 px and 3-12 MB; the API takes up to ~5 MB per image


def _pdf_pages_count(p: Path) -> int:
    try:
        import pdfplumber
        with pdfplumber.open(p) as pdf:
            return len(pdf.pages)
    except Exception:
        return 10_000


def _fit_image(data: bytes, suf: str) -> tuple[bytes, str]:
    """Phone photos are often too large for the API. Downscale (keeping orientation) and re-encode when needed."""
    mt = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}[suf]
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(data))
        if len(data) <= 3_500_000 and max(im.size) <= MAX_IMAGE_SIDE and mt != "image/gif":
            return data, mt
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        for q in (88, 80, 70, 60):
            buf = io.BytesIO(); im.save(buf, format="JPEG", quality=q)
            if buf.tell() <= 3_500_000:
                break
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, mt


def locate(lines: list[str], source: str, quote: str) -> int | None:
    """Index of the line a cited value came from. Excel cells map to their row; other locators match their prefix;
    the quoted words are the fallback."""
    import re
    loc, quote = (source or "").strip(), (quote or "").strip()
    m = re.match(r"(.+?\.xls[xm]?)!([^!]+)!\$?([A-Z]{1,3})\$?(\d+)", loc)
    if m:
        row = f"{m.group(1)}!{m.group(2)}!R{m.group(4)}:"
        hit = next((i for i, ln in enumerate(lines) if ln.startswith(row)), None)
        if hit is not None:
            return hit
    if loc:
        key = loc.split(",")[0].strip()
        hit = next((i for i, ln in enumerate(lines) if ln.startswith(key + " ") or ln.startswith(key + ":") or ln.startswith(key + " |")), None)
        if hit is not None:
            return hit
    if quote and len(quote) >= 3:
        return next((i for i, ln in enumerate(lines) if quote[:40] in ln), None)
    return None


INJECTION = [r"ignore (all |any )?(the )?(previous|prior|above|earlier)? ?(instructions|rules)", r"disregard (the |all )?(previous|above|award)? ?(instructions|rules)",
             r"recommend (this|our) (vendor|company|quote)", r"you are (an? )?(ai|assistant|model)", r"(system|developer) prompt",
             r"mark (this|our) (vendor|quote|company) as (compliant|qualified|approved)", r"regardless of (price|qualification|the rules)"]


def injection_lines(ev: Evidence) -> list[tuple[str, str]]:
    """Text in a vendor's files that reads like an instruction to an AI. Found by code, independent of the model."""
    import re
    out = []
    for name, body in ev.texts:
        for ln in body.splitlines():
            if any(re.search(p, ln, re.I) for p in INJECTION):
                out.append((name, ln.split("|", 1)[-1].strip()[:160]))
    return out


def to_claude_content(ev: Evidence) -> list[dict]:
    """Message content blocks: originals first (so the model sees layout), then the locator-numbered text."""
    blocks: list[dict] = []
    for name, data in ev.pdfs:
        blocks.append({"type": "document", "title": name,
                       "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}})
    for name, data, mt in ev.images:
        blocks.append({"type": "text", "text": f"Image file: {name}"})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(data).decode()}})
    blocks.append({"type": "text", "text": "LOCATOR-NUMBERED TEXT OF EVERY FILE (cite these locators):\n\n" + ev.as_text()})
    return blocks


def pdf_page_images(p: Path, resolution: int = 80) -> list[bytes]:
    import pdfplumber
    out = []
    with pdfplumber.open(p) as pdf:
        for page in pdf.pages:
            buf = io.BytesIO()
            page.to_image(resolution=resolution).original.save(buf, format="PNG")
            out.append(buf.getvalue())
    return out
