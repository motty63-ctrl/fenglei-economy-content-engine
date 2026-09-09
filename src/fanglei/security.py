"""Central redaction for provider errors, URLs, artifacts, and CLI output."""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "authorization", "x-api-key", "x_api_key", "api-key", "api_key", "apikey",
    "key", "token", "access_token", "secret", "signature", "userid", "user_id",
}


def _is_sensitive_key(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized in _SENSITIVE_KEYS or normalized.endswith(("_api_key", "_token", "_secret"))


def sanitize_url(value: str) -> str:
    """Redact credential-like query values while preserving research parameters."""
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"}:
            return value
        query = [
            (name, REDACTED if _is_sensitive_key(name) else item)
            for name, item in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except Exception:
        return REDACTED


def _environment_secrets() -> set[str]:
    return {
        value for name, value in os.environ.items()
        if value and len(value) >= 8 and _is_sensitive_key(name)
    }


def redact_text(value: object) -> str:
    """Return a display-safe message without authentication material."""
    text = str(value)
    text = re.sub(
        r"(?i)([\"']?authorization[\"']?\s*[:=]\s*)([\"']?)([^\"'\r\n,;\]}]+)([\"']?)",
        rf"\1\2{REDACTED}\4",
        text,
    )
    text = re.sub(
        r"(?i)([\"']?(?:x-api-key|x_api_key|api-key|api_key|apikey|access_token|token|secret|signature|userid|user_id)[\"']?\s*[:=]\s*)([\"']?)([^\"'\s,;&\]}]+)([\"']?)",
        rf"\1\2{REDACTED}\4",
        text,
    )
    text = re.sub(r"https?://[^\s\"'<>]+", lambda match: sanitize_url(match.group(0)), text)
    for secret in sorted(_environment_secrets(), key=len, reverse=True):
        for representation in {secret, quote(secret, safe=""), quote_plus(secret)}:
            if representation:
                text = text.replace(representation, REDACTED)
    return text


def safe_error_message(error: BaseException) -> str:
    return redact_text(str(error))
