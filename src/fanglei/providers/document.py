"""Contracts shared by official document adapters and fetchers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FetchContext:
    country: str | None
    years: tuple[str, ...]
    indicators: tuple[str, ...]
    questions: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalTarget:
    method: Literal["api", "pdf", "html"]
    url: str
    safe_url: str
    adapter: str
    request_fingerprint: str
    credential_ref: str | None = None

