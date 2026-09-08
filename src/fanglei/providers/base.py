"""Provider boundary for future model integrations."""

from typing import Protocol

from fanglei.models import AnalysisResult


class AnalysisProvider(Protocol):
    name: str
    prompt_version: str

    def analyze(self, source: str, title: str) -> AnalysisResult:
        """Analyze normalized source text without writing artifacts."""
        ...
