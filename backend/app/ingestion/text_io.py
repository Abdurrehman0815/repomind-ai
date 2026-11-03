"""
RepoMind AI — Source text reading

Single place that turns a file on disk into text safe to store in PostgreSQL.
"""
from __future__ import annotations

import codecs
from pathlib import Path


def read_source_text(path: Path | str) -> str:
    """Read a source file as clean text.

    Handles UTF-16/UTF-8 BOMs (common for Windows-created files such as
    requirements.txt) and strips NUL characters, which PostgreSQL text columns reject.
    """
    raw = Path(path).read_bytes()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = raw.decode("utf-16", errors="replace")
    elif raw.startswith(codecs.BOM_UTF8):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.replace(chr(0), "")
