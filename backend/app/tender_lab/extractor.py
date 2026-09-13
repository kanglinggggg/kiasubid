import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.tender_lab.schemas import DocumentExtractionResponse, DocumentPage

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARACTERS = 120_000
SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_MEMBER_LIMIT = 10_000
DOCX_UNCOMPRESSED_LIMIT = 64 * 1024 * 1024
DOCX_COMPRESSION_RATIO_LIMIT = 1_000


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


def _docx_text(element: ElementTree.Element) -> str:
    word = f"{{{WORD_NAMESPACE}}}"
    pieces: list[str] = []
    for node in element.iter():
        if node.tag == f"{word}t" and node.text:
            pieces.append(node.text)
        elif node.tag == f"{word}tab":
            pieces.append("\t")
        elif node.tag in {f"{word}br", f"{word}cr"}:
            pieces.append("\n")
    return "".join(pieces).strip()


def _validated_docx(raw: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
        members = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise DocumentExtractionError("The DOCX archive is corrupt.") from exc
    names = set(archive.namelist())
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        archive.close()
        raise DocumentExtractionError("The upload is not a valid DOCX document.")
    if len(members) > DOCX_MEMBER_LIMIT:
        archive.close()
        raise DocumentExtractionError("The DOCX contains too many embedded files.")
    total_size = 0
    compressed_size = 0
    for member in members:
        normalised_name = member.filename.replace("\\", "/")
        archive_path = Path(normalised_name)
        parts = archive_path.parts
        if archive_path.is_absolute() or ".." in parts:
            archive.close()
            raise DocumentExtractionError("The DOCX contains an unsafe archive path.")
        total_size += member.file_size
        compressed_size += member.compress_size
        if total_size > DOCX_UNCOMPRESSED_LIMIT:
            archive.close()
            raise DocumentExtractionError("The expanded DOCX exceeds the safe size limit.")
    ratio = total_size / max(compressed_size, 1)
    if total_size > 1_000_000 and ratio > DOCX_COMPRESSION_RATIO_LIMIT:
        archive.close()
        raise DocumentExtractionError("The DOCX compression ratio exceeds the safe limit.")
    return archive


def _extract_docx(raw: bytes) -> tuple[list[DocumentPage], list[str]]:
    archive = _validated_docx(raw)
    try:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (KeyError, ElementTree.ParseError) as exc:
        raise DocumentExtractionError("The DOCX document XML is corrupt.") from exc
    finally:
        archive.close()

    word = f"{{{WORD_NAMESPACE}}}"
    body = root.find(f"{word}body")
    if body is None:
        raise DocumentExtractionError("The DOCX has no readable document body.")
    def block_children(parent: ElementTree.Element):
        """Yield paragraphs/tables through Word content controls in document order."""
        for child in parent:
            if child.tag in {f"{word}p", f"{word}tbl"}:
                yield child
            elif child.tag in {f"{word}sdt", f"{word}sdtContent"}:
                yield from block_children(child)

    blocks: list[str] = []
    for child in block_children(body):
        if child.tag == f"{word}p":
            text = _docx_text(child)
            if text:
                blocks.append(text)
        elif child.tag == f"{word}tbl":
            for row in child.iter(f"{word}tr"):
                cells = [_docx_text(cell) for cell in row.iter(f"{word}tc")]
                text = " | ".join(cell for cell in cells if cell)
                if text:
                    blocks.append(text)
    text = "\n\n".join(blocks).strip()
    if not text:
        raise DocumentExtractionError("The DOCX contains no readable text.")
    return [DocumentPage(page=1, text=text, character_count=len(text))], [
        "DOCX files do not expose reliable page numbers; citations follow document order."
    ]


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
    elif suffix == ".docx" or media_type == DOCX_MEDIA_TYPE:
        pages, warnings = _extract_docx(raw)
        resolved_type = DOCX_MEDIA_TYPE
    elif suffix in SUPPORTED_TEXT_SUFFIXES or media_type.startswith("text/"):
        pages, warnings = _extract_text(raw)
        resolved_type = "text/plain"
    else:
        raise DocumentExtractionError(
            "Only selectable-text PDF, DOCX, TXT and Markdown files are supported."
        )

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
