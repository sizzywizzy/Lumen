"""Screenplay text extraction for the intake dropzone.

The dropzone used to record only a filename, so nothing downstream ever saw the
actual screenplay. This turns an uploaded file into plain text that the agents
can reason over, and it is the single place that knows about file formats.

Formats:
  .txt .fountain .md   plain text, used as-is
  .fdx                 Final Draft XML — paragraphs pulled out in order
  .pdf                 pypdf text extraction (already installed)

Everything is best-effort and non-fatal: an unreadable file returns an error
string rather than raising, so intake never dead-ends on a bad upload.
"""
import base64
import binascii
import hashlib
import io
import re
from typing import Optional
from xml.etree import ElementTree

MAX_CHARS = 400_000
# The keys upload_script writes onto GlobalState.script_context. Phase agents
# that rewrite the context keep these, and a pipeline run carries them over.
INTAKE_KEYS = ("raw_text", "source_filename", "source_format", "char_count", "truncated", "fingerprint")
PLAIN_SUFFIXES = (".txt", ".fountain", ".md", ".markdown", ".text")


class ScriptExtractionError(ValueError):
    """Raised when a file cannot be turned into usable text."""


def _suffix(filename: str) -> str:
    name = (filename or "").lower().strip()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def _from_fdx(raw: bytes) -> str:
    """Final Draft: <Paragraph Type="Action"><Text>…</Text></Paragraph>."""
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise ScriptExtractionError(f"Could not parse the .fdx file: {exc}") from exc

    lines: list[str] = []
    for paragraph in root.iter("Paragraph"):
        text = "".join(node.text or "" for node in paragraph.iter("Text")).strip()
        if not text:
            continue
        kind = (paragraph.get("Type") or "").lower()
        # Keep the shape of a screenplay so the model can read structure.
        if kind in ("scene heading", "shot"):
            lines.append(f"\n{text.upper()}")
        elif kind == "character":
            lines.append(f"\n{text.upper()}")
        elif kind == "parenthetical":
            lines.append(f"({text.strip('()')})")
        else:
            lines.append(text)
    if not lines:
        raise ScriptExtractionError("The .fdx file contained no readable paragraphs.")
    return "\n".join(lines)


def _from_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ScriptExtractionError(
            "PDF support needs the 'pypdf' package (pip install pypdf), or upload "
            "the script as .txt / .fountain / .fdx instead."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 — pypdf raises many shapes
        raise ScriptExtractionError(f"Could not read the PDF: {exc}") from exc

    text = "\n".join(pages).strip()
    if not text:
        raise ScriptExtractionError(
            "No text could be extracted — this PDF is probably a scan. "
            "Upload a text-based PDF, or a .txt / .fountain export."
        )
    return text


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def extract(filename: str, *, text: Optional[str] = None, content_base64: Optional[str] = None) -> dict:
    """Return {text, char_count, fingerprint, format, filename}.

    Callers send either `text` (already plain) or `content_base64` (any format).
    """
    suffix = _suffix(filename)

    if text is not None and text.strip():
        extracted, fmt = _tidy(text), suffix.lstrip(".") or "text"
    elif content_base64:
        try:
            raw = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ScriptExtractionError("The uploaded file could not be decoded.") from exc

        if suffix == ".pdf":
            extracted, fmt = _tidy(_from_pdf(raw)), "pdf"
        elif suffix == ".fdx":
            extracted, fmt = _tidy(_from_fdx(raw)), "fdx"
        elif suffix in PLAIN_SUFFIXES or not suffix:
            extracted, fmt = _tidy(raw.decode("utf-8", errors="replace")), suffix.lstrip(".") or "text"
        else:
            raise ScriptExtractionError(
                f"Unsupported file type '{suffix}'. Use .pdf, .fdx, .fountain or .txt."
            )
    else:
        raise ScriptExtractionError("No file content was supplied.")

    if not extracted:
        raise ScriptExtractionError("The file appears to be empty.")

    truncated = len(extracted) > MAX_CHARS
    if truncated:
        extracted = extracted[:MAX_CHARS]

    return {
        "text": extracted,
        "char_count": len(extracted),
        "truncated": truncated,
        "fingerprint": hashlib.sha256(extracted.encode("utf-8")).hexdigest()[:16],
        "format": fmt,
        "filename": filename,
    }
