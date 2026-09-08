"""Deterministic Phase 1 analysis provider."""

from __future__ import annotations

import re

from fanglei.models import (
    AnalysisResult,
    AuthorArgument,
    FactCandidate,
    ResearchQuestion,
    SingleSourceRisk,
    VerificationClaim,
)


FACT_MARKERS = ("%", "percent", "rate", "gdp", "inflation", "employment", "利率", "通胀", "就业", "政策")
ARGUMENT_MARKERS = ("argues", "claims", "believes", "认为", "主张", "观点")


def _sentences(source: str, title: str) -> list[str]:
    pieces = [piece.strip(" -#\t") for piece in re.split(r"(?<=[。！？.!?])\s+|\n+", source)]
    return [piece for piece in pieces if piece and piece != title]


class MockAnalysisProvider:
    name = "mock"
    prompt_version = "questions-v1"

    def analyze(self, source: str, title: str) -> AnalysisResult:
        sentences = _sentences(source, title)
        fact_sentences = [
            sentence
            for sentence in sentences
            if any(char.isdigit() for char in sentence) or any(marker in sentence.lower() for marker in FACT_MARKERS)
        ]
        argument_sentences = [
            sentence for sentence in sentences if any(marker in sentence.lower() for marker in ARGUMENT_MARKERS)
        ]

        facts = [
            FactCandidate(
                id=f"fact_candidate_{index:03d}",
                statement=sentence,
                kind="economic_data" if any(char.isdigit() for char in sentence) else "economic_claim",
                verification_required=True,
            )
            for index, sentence in enumerate(fact_sentences, start=1)
        ]
        arguments = [
            AuthorArgument(
                id=f"argument_{index:03d}",
                claim=sentence,
                supporting_reasoning="The source presents this as the author's interpretation.",
            )
            for index, sentence in enumerate(argument_sentences, start=1)
        ]
        claims = [
            VerificationClaim(
                id=f"claim_{index:03d}",
                claim=fact.statement,
                reason="The statement concerns economic data, policy, or a measurable economic condition.",
                priority="high",
            )
            for index, fact in enumerate(facts, start=1)
        ]
        questions = [
            ResearchQuestion(
                id="question_001",
                question=f"哪些独立证据可以验证“{title}”涉及的关键事实？",
                purpose="区分原文线索与经过独立核验的经济事实。",
                expected_source_types=["official_statistics", "policy_document", "independent_research"],
            ),
            ResearchQuestion(
                id="question_002",
                question=f"围绕“{title}”的主要因果机制是否得到数据和研究支持？",
                purpose="检验作者观点背后的机制、适用条件和反例。",
                expected_source_types=["academic_research", "institutional_research", "independent_data"],
            ),
        ]
        risks = [
            SingleSourceRisk(
                description="当前分析仅来自输入文章，所有事实和观点仍存在单一来源依赖。",
                related_claim_ids=[claim.id for claim in claims],
                severity="high",
            )
        ]
        return AnalysisResult(
            core_topic=title,
            key_facts=facts,
            author_arguments=arguments,
            claims_requiring_external_verification=claims,
            research_questions=questions,
            single_source_dependency_risks=risks,
        )
