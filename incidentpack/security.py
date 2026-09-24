"""Credential-pattern redaction shared by reports and operational logging."""

from __future__ import annotations

import re

_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+\-/=]+"),
    re.compile(r"(?i)(authorization\s*:\s*basic\s+)[A-Za-z0-9+/=]+"),
    re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+\-/=]{16,}"),
    re.compile(
        r"(?i)(\b(?:password|passwd|api[_-]?key|access[_-]?token|token|secret)\s*[:=]\s*)"
        r"[^\s,;&]+"
    ),
)


def redact_secret_text(value: str) -> str:
    """Redact recognizable credential patterns while preserving surrounding diagnostics."""
    redacted = value
    for pattern in _SECRET_VALUE_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
    return redacted
