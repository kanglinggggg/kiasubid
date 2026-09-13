import io
import zipfile

import pytest
from app.tender_lab.extractor import DocumentExtractionError, extract_document


def _docx(document_xml: str) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="xml" ContentType="application/xml"/>
            </Types>""",
        )
        archive.writestr("word/document.xml", document_xml)
    return target.getvalue()


def test_docx_extraction_keeps_paragraph_and_table_order() -> None:
    raw = _docx(
        """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>The supplier shall provide a secure portal.</w:t></w:r></w:p>
            <w:tbl><w:tr>
              <w:tc><w:p><w:r><w:t>Milestone</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:r><w:t>Prototype acceptance</w:t></w:r></w:p></w:tc>
            </w:tr></w:tbl>
          </w:body>
        </w:document>"""
    )

    result = extract_document(
        filename="tender.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        raw=raw,
    )

    assert result.content_type.endswith("wordprocessingml.document")
    assert result.page_count == 1
    assert "The supplier shall provide a secure portal." in result.text
    assert "Milestone | Prototype acceptance" in result.text
    assert "do not expose reliable page numbers" in result.warnings[0]


def test_docx_extraction_reads_content_control_wrapped_blocks_and_cells() -> None:
    raw = _docx(
        """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:sdt><w:sdtContent>
              <w:p><w:r><w:t>Evaluation criteria</w:t></w:r></w:p>
            </w:sdtContent></w:sdt>
            <w:tbl><w:tr>
              <w:sdt><w:sdtContent><w:tc><w:p><w:r><w:t>Skills and experience</w:t></w:r></w:p></w:tc></w:sdtContent></w:sdt>
              <w:sdt><w:sdtContent><w:tc><w:p><w:r><w:t>Provide three references</w:t></w:r></w:p></w:tc></w:sdtContent></w:sdt>
            </w:tr></w:tbl>
          </w:body>
        </w:document>"""
    )

    result = extract_document(
        filename="controlled-tender.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        raw=raw,
    )

    assert "Evaluation criteria" in result.text
    assert "Skills and experience | Provide three references" in result.text


def test_invalid_docx_fails_closed() -> None:
    with pytest.raises(DocumentExtractionError, match="corrupt"):
        extract_document(
            filename="tender.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            raw=b"not a zip archive",
        )
