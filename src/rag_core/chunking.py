from __future__ import annotations

from typing import Iterable, List, Tuple


def _split_paragraphs(text: str) -> List[str]:
    parts = [p for p in text.replace("\r\n", "\n").split("\n\n")]
    return parts if parts else [text]


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[Tuple[int, str]]:
    """Chunk text by paragraphs with soft max length and overlap.

    Returns list of (index, chunk_text) tuples.
    """
    if chunk_size <= 0:
        return [(0, text)]

    paras = _split_paragraphs(text)
    chunks: List[str] = []
    buf: List[str] = []
    cur_len = 0
    for p in paras:
        # ensure paragraph ends with newline to keep some structure
        pp = p if p.endswith("\n") else p + "\n"
        if cur_len + len(pp) > chunk_size and buf:
            chunks.append("".join(buf).strip())
            # prepare overlap: keep tail of last chunk
            tail = chunks[-1][-overlap:] if overlap > 0 else ""
            buf = [tail, pp]
            cur_len = len(tail) + len(pp)
        else:
            buf.append(pp)
            cur_len += len(pp)
    if buf:
        chunks.append("".join(buf).strip())

    return list(enumerate(chunks))

