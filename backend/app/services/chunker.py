"""Simple text chunker. Splits by paragraphs then merges to target size."""
import re


def chunk_text(text: str, target_size: int = 500, overlap: int = 50) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    # Split by blank lines first
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= target_size:
            buf = (buf + "\n" + p) if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= target_size:
                buf = p
            else:
                # hard split long paragraph
                for i in range(0, len(p), target_size - overlap):
                    chunks.append(p[i : i + target_size])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks
