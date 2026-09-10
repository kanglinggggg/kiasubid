from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.tender_lab.schemas import DocumentExtractionResponse, DocumentPage

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARACTERS = 120_000
SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


class DocumentExtractionError(ValueError):
    """Raised when a supplied document cannot be safely converted to text."""


def _clip_pages(pages: list[DocumentPage]) -> tuple[list[DocumentPage], bool]:
    remaining = MAX_TEXT_CHARACTERS
    clipped: list[DocumentPage] = []
    truncated = False
    for page in pages:
        if remaining <= 0:
            truncated = True
            break
        text = page.text
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        clipped.append(
            DocumentPage(page=page.page, text=text, character_count=len(text))
        )
        remaining -= len(text)
    if len(clipped) < len(pages):
        truncated = True
    return clipped, truncated


def _extract_pdf(filename: str, raw: bytes) -> tuple[list[DocumentPage], list[str]]:
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:  # pypdf exposes several encryption-specific errors.
                raise DocumentExtractionError(
                    "Encrypted PDF could not be opened. Supply an unlocked copy."
                ) from exc
            if not unlocked:
                raise DocumentExtractionError(
                    "Encrypted PDF could not be opened. Supply an unlocked copy."
                )
        if not reader.pages:
            raise DocumentExtractionError("The PDF has no readable pages.")
        pages: list[DocumentPage] = []
        blank_pages: list[int] = []
        for number, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                text = ""
            if not text:
                blank_pages.append(number)
            pages.append(DocumentPage(page=number, text=text, character_count=len(text)))
    except DocumentExtractionError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise DocumentExtractionError(f"{filename} is not a readable PDF.") from exc

    warnings: list[str] = []
    if blank_pages:
        warnings.append(
            "No selectable text was found on page(s) "
            + ", ".join(str(page) for page in blank_pages[:12])
            + ". Scanned pages require OCR and remain unreviewed."
        )
    if not any(page.text for page in pages):
        raise DocumentExtractionError(
            "No selectable text was found. This looks like a scanned PDF; OCR is not enabled."
        )
    return pages, warnings


def _extract_text(raw: bytes) -> tuple[list[DocumentPage], list[str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentExtractionError("Text files must use UTF-8 encoding.") from exc
    if not text.strip():
        raise DocumentExtractionError("The uploaded text file is empty.")
    return [DocumentPage(page=1, text=text.strip(), character_count=len(text.strip()))], []


def extract_document(
    *, filename: str, content_type: str | None, raw: bytes
) -> DocumentExtractionResponse:
    """Extract text in memory. The upload is never persisted by this module."""
    if not raw:
        raise DocumentExtractionError("The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise DocumentExtractionError("File exceeds the 8 MB upload limit.")

    safe_name = Path(filename or "upload").name
    suffix = Path(safe_name).suffix.casefold()
    media_type = (content_type or "application/octet-stream").casefold()
    if suffix == ".pdf" or media_type == "application/pdf":
        pages, warnings = _extract_pdf(safe_name, raw)
        resolved_type = "application/pdf"
    elif suffix in SUPPORTED_TEXT_SUFFIXES or media_type.startswith("text/"):
        pages, warnings = _extract_text(raw)
        resolved_type = "text/plain"
    else:
        raise DocumentExtractionError("Only selectable-text PDF, TXT and Markdown files are supported.")

    clipped_pages, truncated = _clip_pages(pages)
    if truncated:
        warnings.append("Extracted text was truncated at 120,000 characters.")
    combined = "\n\n".join(
        f"[Page {page.page}]\n{page.text}" for page in clipped_pages if page.text
    )
    return DocumentExtractionResponse(
        filename=safe_name,
        content_type=resolved_type,
        page_count=len(pages),
        character_count=sum(page.character_count for page in clipped_pages),
        text=combined,
        pages=clipped_pages,
        truncated=truncated,
        warnings=warnings,
    )
