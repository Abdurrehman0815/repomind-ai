"""Prompt-boundary protections for untrusted repository and user text."""
from __future__ import annotations
import re

INJECTION_PATTERNS = (r"ignore (all |previous |prior )?instructions", r"system prompt", r"reveal (your |the )?(secret|instructions)", r"you are now")
SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[=:]\s*[^\s,;]+")

def sanitize_untrusted_text(text: str, max_chars: int = 12000) -> str:
    safe = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text[:max_chars])
    for pattern in INJECTION_PATTERNS:
        safe = re.sub(pattern, "[UNTRUSTED_INSTRUCTION_REMOVED]", safe, flags=re.IGNORECASE)
    return safe

def is_suspicious_instruction(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in INJECTION_PATTERNS)
