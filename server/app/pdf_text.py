"""Plain text from a saved PDF, for the AI summary. Bounded: a page cap and a
character cap, so a huge or hostile PDF can't stall the server."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pypdf import PdfReader

MAX_PAGES = 40
MAX_CHARS = 60_000

# pypdf logs a warning per malformed object; the caller only needs the text.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PdfTextError(Exception):
    pass


def extract_text(
    path: Path, max_pages: int = MAX_PAGES, max_chars: int = MAX_CHARS
) -> tuple[str, bool]:
    """(text, truncated). Blocking: run it in a worker thread."""
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfTextError("the PDF is encrypted")
        parts: list[str] = []
        size = 0
        truncated = len(reader.pages) > max_pages
        for page in reader.pages[:max_pages]:
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            parts.append(text)
            size += len(text) + 2
            if size >= max_chars:
                truncated = True
                break
    except PdfTextError:
        raise
    except Exception as e:  # pypdf raises many types on malformed files
        raise PdfTextError(f"could not read the PDF ({type(e).__name__})") from e
    return "\n\n".join(parts)[:max_chars], truncated


# pypdf is CPU-bound and can hold a lot of memory on big files: at most this many
# extractions run at once (AI summary, PDF full-text index); the rest wait.
MAX_PARALLEL = 2
_slots = asyncio.Semaphore(MAX_PARALLEL)


async def extract_text_async(
    path: Path, max_pages: int = MAX_PAGES, max_chars: int = MAX_CHARS
) -> tuple[str, bool]:
    """extract_text in a worker thread, at most MAX_PARALLEL at a time."""
    async with _slots:
        return await asyncio.to_thread(extract_text, path, max_pages, max_chars)
