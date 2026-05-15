"""Document parsing for common formats."""
from io import BytesIO


def parse_bytes(data: bytes, mime_type: str, filename: str = "") -> str:
    name = (filename or "").lower()
    mt = (mime_type or "").lower()

    if name.endswith(".pdf") or "pdf" in mt:
        return _parse_pdf(data)
    if name.endswith(".docx") or "officedocument.wordprocessingml" in mt:
        return _parse_docx(data)
    if name.endswith(".md") or name.endswith(".markdown"):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".html") or "html" in mt:
        return _parse_html(data)
    # default: text
    return data.decode("utf-8", errors="ignore")


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def _parse_docx(data: bytes) -> str:
    import docx
    doc = docx.Document(BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _parse_html(data: bytes) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n").strip()
