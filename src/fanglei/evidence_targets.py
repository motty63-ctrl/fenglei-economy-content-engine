"""Run-bound evidence targets and deterministic source-span extraction.

Targets describe what a case is looking for. They are retrieval and scope
metadata only; every emitted candidate remains bound to exact captured text
and must pass the ordinary evidence and claim-verification gates.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Mapping

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from fanglei.research import FetchedDocument


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlank = Annotated[str, StringConstraints(strict=True, min_length=1), AfterValidator(_nonblank)]
EvidenceKind = Literal["narrative_sentence", "table_cell", "revision"]


class EvidenceAuthorityScopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    subject: NonBlank
    measure: NonBlank
    period: NonBlank
    unit: NonBlank | None
    statistic: NonBlank | None
    certainty: NonBlank


class EvidenceTargetV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    target_id: NonBlank
    concept: NonBlank
    aliases: list[NonBlank] = Field(min_length=1)
    periods: list[NonBlank] = Field(min_length=1)
    source_roles: list[NonBlank] = Field(min_length=1)
    statistic: NonBlank | None
    expected_unit_family: NonBlank | None
    evidence_kinds: list[EvidenceKind] = Field(min_length=1)
    authority_scope: EvidenceAuthorityScopeV1
    required_source_section: NonBlank | None = None


class EvidenceTargetSetV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["evidence-targets/1.0"]
    run_id: NonBlank
    case_id: NonBlank
    targets: list[EvidenceTargetV1] = Field(min_length=1)

    @field_validator("targets")
    @classmethod
    def _validate_unique_ids(cls, value: list[EvidenceTargetV1]) -> list[EvidenceTargetV1]:
        ids = [item.target_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("target_id values must be unique")
        return value


def parse_evidence_target_set(
    value: EvidenceTargetSetV1 | Mapping[str, object], *, run_id: str, case_id: str
) -> EvidenceTargetSetV1:
    """Parse a strict target contract and require explicit active identities."""
    parsed = value if isinstance(value, EvidenceTargetSetV1) else EvidenceTargetSetV1.model_validate(value)
    if parsed.run_id != run_id:
        raise ValueError("evidence target run_id does not match the active run")
    if parsed.case_id != case_id:
        raise ValueError("evidence target case_id does not match the active case")
    return parsed


_NUMBER = re.compile(r"(?<![\w.])(?:\$\s*)?[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![\w]|\.(?=\d))")
_UNIT_AFTER = re.compile(
    r"^\s*(percent(?:age)?(?:\s+points?)?|hours?|minutes?|seconds?|cents?|"
    r"dollars?|euros?|pounds?|thousands?|millions?|billions?|jobs?|workers?|"
    r"employees?|persons?|people|units?|index\s+points?)\b",
    re.IGNORECASE,
)
_MONTH = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"^(?:19|20)\d{2}(?:\s*\([^)]*\))?$", re.IGNORECASE)
_PIPE_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_TABLE_TITLE = re.compile(
    r"^(?:(?:summary\s+)?table\s+[A-Z0-9]+(?:-[A-Z0-9]+)*\s*\.\s*.+|"
    r"table\s+[A-Z0-9]+(?:-[A-Z0-9]+)*\s*\.?\s*)$",
    re.IGNORECASE,
)
_TERMINAL_LINE = re.compile(r"[.!?。！？][\"'’”)}\]]*\s*$")
_SENTENCE_BOUNDARY = re.compile(r"(?P<end>[.!?。！？][\"'’”)}\]]*)\s+(?=[A-Z0-9“‘\"(])")
_COORDINATED_CLAUSE_BOUNDARY = re.compile(r",\s+(?:and|but|while|whereas)\s+|;\s*", re.IGNORECASE)
_FINITE_PREDICATE = re.compile(
    r"^(?:(?:the|a|an|this|that|these|those|it|they|we|he|she)\s+)?"
    r"[A-Za-z][\w'-]*(?:\s+(?:[A-Za-z][\w'-]*|of|in|for|to|by|from|the|a|an)){0,7}\s+"
    r"(?:am|is|are|was|were|be|been|being|has|have|had|will|would|can|could|may|might|must|shall|should|"
    r"do|does|did|[A-Za-z][\w'-]*(?:ed|s))\b",
    re.IGNORECASE,
)
_NON_PROPOSITIONAL_COMMA_TAIL = re.compile(
    r",\s+(?:(?:[A-Za-z][\w'-]*ly\s+)?[A-Za-z][\w'-]*ing\b|"
    r"(?:well|far|slightly|substantially|much|somewhat)\s+(?:above|below|higher|lower|more|less)\b|"
    r"compared\s+with\b|relative\s+to\b|following\b|which\b|although\b|despite\b)",
    re.IGNORECASE,
)
_COMMON_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.",
    "u.s.", "u.k.", "e.g.", "i.e.", "etc.", "vs.", "no.", "fig.",
    "inc.", "corp.", "dept.", "approx.", "est.",
}
_REVISION_FULL = re.compile(
    r"\brevised\s+(up|down)\s+by\s+([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s*,?\s*from\s+([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s+to\s+([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)",
    re.IGNORECASE,
)
_REVISION_DIRECTION = re.compile(
    r"\brevised\s+(up|down)\s+by\s+([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)",
    re.IGNORECASE,
)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _line_locator(start: int, end: int) -> str:
    return f"line:{start}" if start == end else f"line:{start}-{end}"


def _is_heading_line(value: str) -> bool:
    stripped = value.strip()
    if (
        stripped.startswith("#")
        or re.match(r"^(?:summary\s+)?table\s+[A-Z0-9]", stripped, re.I)
        or re.match(r"^(?:footnotes?|notes?)\s*:", stripped, re.I)
    ):
        return True
    # A title-cased/all-caps standalone line is a paragraph boundary. A normal
    # prose continuation typically capitalizes only its first word.
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", stripped)
    return bool(
        len(words) >= 2
        and not re.search(r"[.!?。！？,;:]\s*$", stripped)
        and (stripped.isupper() or all(word[:1].isupper() for word in words))
    )


def _explicit_values(text: str) -> list[dict[str, str | None]]:
    values: list[dict[str, str | None]] = []
    for match in _NUMBER.finditer(text):
        token = match.group(0).strip()
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            continue
        if token.endswith("%"):
            unit = "percent"
        elif token.startswith("$"):
            unit = "$"
        else:
            unit_match = _UNIT_AFTER.match(text[match.end() :])
            unit = _normalized(unit_match.group(1)) if unit_match else None
        values.append({"value": token, "unit": unit})
    return values


def _looks_like_independent_clause(text: str) -> bool:
    """Recognize a coordinated subject/predicate without splitting value lists."""
    return _FINITE_PREDICATE.match(text.strip()) is not None


def atomic_proposition_spans(text: str) -> list[dict[str, object]]:
    """Return deterministic sentence-level proposition spans with exact offsets.

    Evidence remains the complete captured sentence. Coordinated independent
    clauses are split; comma-led comparative or participial tails are excluded
    from the claim proposition while value continuations such as ``or 0.3%``
    and ``to $37`` remain attached to the same metric.
    """
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for boundary in _COORDINATED_CLAUSE_BOUNDARY.finditer(text):
        if _looks_like_independent_clause(text[boundary.end():]):
            ranges.append((cursor, boundary.start()))
            cursor = boundary.end()
    ranges.append((cursor, len(text)))

    output: list[dict[str, object]] = []
    for raw_start, raw_end in ranges:
        start, end = raw_start, raw_end
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        local = text[start:end]
        adjunct = _NON_PROPOSITIONAL_COMMA_TAIL.search(local)
        if adjunct is not None:
            end = start + adjunct.start()
            while end > start and text[end - 1].isspace():
                end -= 1
        if start < end:
            output.append({"start": start, "end": end, "text": text[start:end]})
    return output


def validate_proposition_span(evidence_text: str, value: object) -> dict[str, object] | None:
    """Validate an exact code-point span contained by the full evidence text."""
    if not isinstance(value, dict) or set(value) != {"start", "end", "text"}:
        return None
    start, end, selected = value.get("start"), value.get("end"), value.get("text")
    if (
        not isinstance(start, int) or isinstance(start, bool)
        or not isinstance(end, int) or isinstance(end, bool)
        or not isinstance(selected, str)
        or start < 0 or end <= start or end > len(evidence_text)
        or evidence_text[start:end] != selected
        or selected != selected.strip()
    ):
        return None
    return {"start": start, "end": end, "text": selected}


def is_atomic_narrative_proposition(evidence_text: str, span: object) -> bool:
    """Require a targeted narrative proposition to equal one deterministic atom."""
    parsed = validate_proposition_span(evidence_text, span)
    if parsed is None:
        return False
    return any(
        candidate["start"] == parsed["start"]
        and candidate["end"] == parsed["end"]
        and candidate["text"] == parsed["text"]
        for candidate in atomic_proposition_spans(evidence_text)
    )


def canonical_table_proposition(attribution: str, scope: EvidenceAuthorityScopeV1, context: Mapping[str, object]) -> str:
    """Render one table cell as a deterministic, scope-bound proposition."""
    value = context.get("value")
    if not isinstance(value, str):
        raise ValueError("table proposition requires a selected cell value")
    statistic = f"{scope.statistic} " if scope.statistic else ""
    unit = f" {context['unit']}" if isinstance(context.get("unit"), str) else ""
    return (
        f"{attribution}: reported {statistic}{scope.measure} for "
        f"{scope.subject} ({scope.period}) at {value}{unit}."
    )


def _target_aliases(target: EvidenceTargetV1) -> list[str]:
    """Use only each alias's first atom so a noisy trailing clause cannot select itself."""
    output: list[str] = []
    for alias in target.aliases:
        spans = atomic_proposition_spans(alias)
        selected = str(spans[0]["text"]) if spans else alias
        selected = re.sub(r"^(?:and|but|while|whereas)\s+", "", selected, flags=re.IGNORECASE)
        if selected:
            output.append(selected)
    return output


def _matches_target_alias(target: EvidenceTargetV1, text: str) -> bool:
    folded = _normalized(text)
    return any(_normalized(alias) in folded for alias in _target_aliases(target))


def _revision_values(text: str, *, period: str | None = None) -> dict[str, str | None] | None:
    full_matches = list(_REVISION_FULL.finditer(text))
    direction_matches = list(_REVISION_DIRECTION.finditer(text))
    matches = full_matches or direction_matches
    if period is not None:
        selected = None
        previous_end = 0
        for match in matches:
            clause_prefix = text[previous_end : match.start()]
            if re.search(rf"(?<!\w){re.escape(period)}(?!\w)", clause_prefix, re.IGNORECASE):
                selected = match
                break
            previous_end = match.end()
        if selected is None:
            return None
    else:
        selected = matches[0] if matches else None
    if selected is not None:
        if selected.re is _REVISION_FULL:
            return {
                "previous_value": selected.group(3),
                "revised_value": selected.group(4),
                "revision_amount": selected.group(2),
                "direction": selected.group(1).casefold(),
            }
        return {
            "previous_value": None,
            "revised_value": None,
            "revision_amount": selected.group(2),
            "direction": selected.group(1).casefold(),
        }
    return None


def _is_sentence_abbreviation(prefix: str) -> bool:
    token = re.search(r"(?:[A-Za-z]\.)+[A-Za-z]?\.?$|[A-Za-z]+\.$", prefix)
    if token is None:
        return False
    value = token.group(0).casefold()
    return value in _COMMON_ABBREVIATIONS or bool(re.fullmatch(r"(?:[a-z]\.){1,4}", value))


def _locator_for_span(block_start_line: int, block: str, start: int, end: int) -> str:
    line_offsets = [0]
    for match in re.finditer("\n", block):
        line_offsets.append(match.end())
    first_index = max(index for index, offset in enumerate(line_offsets) if offset <= start)
    last_index = max(index for index, offset in enumerate(line_offsets) if offset < end)
    first_line = block_start_line + first_index
    last_line = block_start_line + last_index
    base = _line_locator(first_line, last_line)
    selected_start = line_offsets[first_index]
    selected_end = len(block) if last_index + 1 >= len(line_offsets) else line_offsets[last_index + 1] - 1
    selected = block[selected_start:selected_end]
    if block[start:end] == selected:
        return base
    return f"{base};columns:{start - selected_start}-{end - selected_start}"


def resolve_text_locator(text: str, locator: str) -> str | None:
    """Resolve a line locator, optionally narrowed by zero-based text columns.

    ``columns`` offsets apply to the newline-joined physical line range. This
    lets a locator identify one sentence on a line that also contains adjacent
    sentences, while preserving wrapped sentence text exactly.
    """
    match = re.fullmatch(r"line:(\d+)(?:-(\d+))?(?:;columns:(\d+)-(\d+))?", locator)
    if match is None:
        return None
    first = int(match.group(1))
    last = int(match.group(2) or first)
    if first < 1 or last < first:
        return None
    lines = text.splitlines()
    if last > len(lines):
        return None
    excerpt = "\n".join(lines[first - 1:last])
    if match.group(3) is None:
        return excerpt
    start, end = int(match.group(3)), int(match.group(4))
    if start < 0 or end <= start or end > len(excerpt):
        return None
    return excerpt[start:end]


def _paragraph_spans(text: str) -> list[tuple[str, str, str | None, str | None]]:
    """Return complete sentence spans with exact line/column locators.

    Wrapped physical lines remain joined inside a sentence. Blank lines and
    structural headings terminate a block, and unfinished trailing text is
    discarded rather than stitched to another paragraph.
    """
    lines = text.splitlines()
    blocks: list[tuple[int, str, str | None, str | None]] = []
    start: int | None = None
    active_heading: str | None = None
    active_heading_locator: str | None = None
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            if start is not None:
                blocks.append((start, "\n".join(lines[start - 1:number - 1]), active_heading, active_heading_locator))
                start = None
            continue
        if _is_heading_line(stripped):
            if start is not None:
                blocks.append((start, "\n".join(lines[start - 1:number - 1]), active_heading, active_heading_locator))
            start = None
            active_heading = line
            active_heading_locator = _line_locator(number, number)
            continue
        if start is None:
            start = number
    if start is not None:
        blocks.append((start, "\n".join(lines[start - 1:]), active_heading, active_heading_locator))

    spans: list[tuple[str, str, str | None, str | None]] = []
    for block_start, block, source_section, source_section_locator in blocks:
        cursor = 0
        for boundary in _SENTENCE_BOUNDARY.finditer(block):
            end = boundary.start("end") + len(boundary.group("end"))
            if boundary.group("end").endswith(".") and _is_sentence_abbreviation(block[:end]):
                continue
            sentence_start = cursor
            while sentence_start < end and block[sentence_start].isspace():
                sentence_start += 1
            if sentence_start < end:
                excerpt = block[sentence_start:end]
                locator = _locator_for_span(block_start, block, sentence_start, end)
                spans.append((locator, excerpt, source_section, source_section_locator))
            cursor = boundary.end()
        end = len(block)
        while end > cursor and block[end - 1].isspace():
            end -= 1
        sentence_start = cursor
        while sentence_start < end and block[sentence_start].isspace():
            sentence_start += 1
        if sentence_start < end and _TERMINAL_LINE.search(block[sentence_start:end]):
            excerpt = block[sentence_start:end]
            locator = _locator_for_span(block_start, block, sentence_start, end)
            spans.append((locator, excerpt, source_section, source_section_locator))
    return spans


def _period_matches(target: EvidenceTargetV1, text: str) -> list[str]:
    folded = _normalized(text)
    return [period for period in target.periods if _normalized(period) in folded]


def _matches_alias(target: EvidenceTargetV1, text: str) -> bool:
    folded = _normalized(text)
    return any(_normalized(alias) in folded for alias in target.aliases)


def _targeted_record(
    document: FetchedDocument,
    target: EvidenceTargetV1,
    *,
    evidence_text: str,
    proposition_span: dict[str, object] | None,
    locator: str,
    kind: str,
    period_matches: list[str],
    table_context: dict[str, object] | None = None,
    target_set_sha256: str | None = None,
    revision_values: dict[str, str | None] | None = None,
    source_section: str | None = None,
    source_section_locator: str | None = None,
) -> dict[str, object]:
    proposition_text = str(proposition_span["text"]) if proposition_span is not None else evidence_text
    explicit_values = _explicit_values(proposition_text)
    claim_values = [item["value"] for item in explicit_values]
    if table_context is not None:
        table_value = table_context.get("value")
        table_unit = table_context.get("unit")
        if isinstance(table_value, str):
            claim_values = [table_value]
            explicit_values = [{
                "value": table_value,
                "unit": table_unit if isinstance(table_unit, str) else None,
            }]
    row: dict[str, object] = {
        "source_id": document.source_id,
        "evidence_text": evidence_text,
        "source_section": table_context.get("source_section") if table_context else source_section,
        "paragraph_locator": locator,
        "published_at": document.published_at,
        "retrieved_at": document.retrieved_at,
        "original_url": document.original_url or document.url,
        "relation": "supports",
        "claim_type": "fact",
        "claim_key": f"evidence-target|{target.target_id}|{document.source_id}|{locator}",
        "claim_values": claim_values,
        "document_hash": document.document_hash,
        "document_format": document.document_format,
        "evidence_origin": "original_document",
        "evidence_target_id": target.target_id,
        "evidence_target_sha256": target_set_sha256,
        "evidence_target_concept": target.concept,
        "evidence_kind": kind,
        "evidence_period_matches": period_matches,
        "explicit_values": explicit_values,
        "authority_scope_candidate": target.authority_scope.model_dump(mode="json"),
    }
    if proposition_span is not None:
        row["proposition_span"] = proposition_span
    if source_section_locator is not None:
        row["source_section_locator"] = source_section_locator
    revision = revision_values if kind == "revision" else None
    if revision is not None:
        row["revision_values"] = revision
    if table_context is not None:
        row["table_context"] = table_context
        row["table_binding"] = table_context
    return row


def _split_pipe_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def _is_number_cell(value: str) -> bool:
    cleaned = value.strip().replace("−", "-")
    return bool(re.fullmatch(r"(?:\$\s*)?[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?", cleaned))


def _pipe_table_rows(
    document: FetchedDocument, lines: list[str], title_line: int, title: str
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    i = title_line
    while i < len(lines):
        if "|" not in lines[i]:
            i += 1
            continue
        block_start = i
        block: list[tuple[int, str, list[str]]] = []
        while i < len(lines) and "|" in lines[i]:
            cells = _split_pipe_row(lines[i])
            if cells and all(_PIPE_SEPARATOR.fullmatch(cell) for cell in cells):
                i += 1
                continue
            block.append((i + 1, lines[i], cells))
            i += 1
        first_data = next(
            (
                index
                for index, (_, _, cells) in enumerate(block)
                if index > 0
                and len(cells) >= 2
                and re.search(r"[A-Za-z\u0080-\uffff]", cells[0])
                and all(_is_number_cell(value) for value in cells[1:])
                and not all(
                    re.fullmatch(r"(?:19|20)\d{2}|Q[1-4]|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?", value, re.I)
                    for value in cells[1:]
                )
            ),
            None,
        )
        if first_data is None or first_data < 1:
            continue
        header_rows = [cells for _, _, cells in block[:first_data]]
        width = len(block[first_data][2])
        if width < 2 or any(len(row) != width for row in header_rows):
            continue
        header_matrix = [row[1:] for row in header_rows]
        if not header_matrix or any(len(row) != width - 1 for row in header_matrix):
            continue
        separator_invalid = any(
            value and not re.search(r"\d|Q[1-4]|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", value, re.I)
            for row in header_matrix for value in row
        )
        if separator_invalid:
            continue
        header_locator = _line_locator(block[0][0], block[first_data - 1][0])
        header_excerpt = "\n".join(raw for _, raw, _ in block[:first_data])
        explicit_unit = _find_unit(lines[max(0, block_start - 4) : block_start])
        for line_number, raw, cells in block[first_data:]:
            if len(cells) != width or not all(_is_number_cell(value) for value in cells[1:]):
                continue
            row_label = cells[0]
            if not row_label or not re.search(r"[A-Za-z\u0080-\uffff]", row_label):
                continue
            for column_index, value in enumerate(cells[1:]):
                path = [row[column_index] for row in header_matrix if row[column_index]]
                period_parts = [part for part in path if re.search(r"(?:19|20)\d{2}|Q[1-4]|January|February|March|April|May|June|July|August|September|October|November|December|Jan\.|Feb\.|Mar\.|Apr\.|Jun\.|Jul\.|Aug\.|Sep\.|Oct\.|Nov\.|Dec\.", part, re.I)]
                period = " ".join(period_parts).strip()
                unit = explicit_unit
                if unit is None:
                    unit = _unit_from_header_or_value(" ".join(path + [value]))
                table_context: dict[str, object] = {
                    "table_contract": "generic-table/1.0",
                    "table_identity": title,
                    "table_title": title,
                    "table_signature": _normalized(title),
                    "source_section": title,
                    "row_label": row_label,
                    "row_path": [row_label],
                    "column_header_path": path,
                    "period": period,
                    # Stub-column headings name the row dimension; they are
                    # not assumed to be a statistic such as a median or rate.
                    "statistic": None,
                    "unit": unit,
                    "value": value,
                    "header_locator": header_locator,
                    "cell_locator": _line_locator(line_number, line_number),
                    "row_locator": _line_locator(line_number, line_number),
                    "header_excerpt": header_excerpt,
                }
                output.append({
                    "source_id": document.source_id,
                    "evidence_text": raw,
                    "source_section": title,
                    "paragraph_locator": f"{_line_locator(line_number, line_number)}; header={header_locator}",
                    "published_at": document.published_at,
                    "retrieved_at": document.retrieved_at,
                    "original_url": document.original_url or document.url,
                    "relation": "supports",
                    "claim_type": "fact",
                    "claim_key": "generic-table|" + "|".join((_normalized(title), _normalized(row_label), _normalized(" ".join(path)))),
                    "claim_values": [value],
                    "document_hash": document.document_hash,
                    "document_format": document.document_format,
                    "evidence_origin": "original_document",
                    "table_context": table_context,
                })
    return output


def _find_unit(lines: list[str]) -> str | None:
    for line in reversed(lines):
        match = re.search(r"\b(?:in\s+)?(thousands?|millions?|billions?|percent(?:age)?(?:\s+points?)?|hours?|dollars?|index\s+points?)\b", line, re.I)
        if match:
            return _normalized(match.group(1))
        explicit = re.search(r"\bunit\s*:\s*([^|]+)$", line, re.I)
        if explicit:
            return _normalized(explicit.group(1))
    return None


def _unit_from_header_or_value(text: str) -> str | None:
    if "$" in text:
        return "$"
    if "%" in text:
        return "percent"
    match = re.search(
        r"\b(percent(?:age)?(?:\s+points?)?|hours?|minutes?|seconds?|cents?|dollars?|euros?|"
        r"pounds?|thousands?|millions?|billions?|jobs?|workers?|employees?|persons?|people|units?|"
        r"index\s+points?)\b",
        text,
        re.IGNORECASE,
    )
    return _normalized(match.group(1)) if match else None


def _line_cell_tables(document: FetchedDocument) -> list[dict[str, object]]:
    lines = document.text.splitlines()
    output: list[dict[str, object]] = []
    title_positions = [i for i, line in enumerate(lines) if _TABLE_TITLE.match(line.strip())]
    for title_index in title_positions:
        title = lines[title_index].strip()
        end = next(
            (
                i for i in range(title_index + 1, len(lines))
                if _TABLE_TITLE.match(lines[i].strip())
                or re.match(r"^(?:Footnotes?|Notes?\s*:|Last Modified Date:)", lines[i].strip(), re.I)
            ),
            len(lines),
        )
        table_lines = [(i, lines[i].strip()) for i in range(title_index + 1, end) if lines[i].strip()]
        date_groups: list[tuple[int, str]] = []
        j = 0
        while j + 1 < len(table_lines):
            month_line = table_lines[j][1]
            year_line = table_lines[j + 1][1]
            if _MONTH.fullmatch(month_line) and _YEAR.fullmatch(year_line):
                date_groups.append((j, f"{month_line} {year_line}"))
                j += 2
            elif date_groups:
                break
            else:
                j += 1
        if len(date_groups) < 2:
            continue
        header_start = date_groups[0][0]
        header_end = date_groups[-1][0] + 2
        column_width = len(date_groups)
        header_positions = [position for start_position, _ in date_groups for position in (start_position, start_position + 1)]
        header_lines = [table_lines[position] for position in header_positions]
        header_physical = [index + 1 for index, _ in header_lines]
        header_locator = _line_locator(header_physical[0], header_physical[-1]) if header_physical else ""
        header_excerpt = "\n".join(
            table_lines[position][1] for position in range(header_positions[0], header_positions[-1] + 1)
        )
        explicit_unit = _find_unit([line for _, line in table_lines[max(0, header_start - 8) : header_start]])
        section_stack: list[str] = []
        current_statistic: str | None = None
        remaining = table_lines[header_end:]
        k = 0
        while k < len(remaining):
            physical_index, label = remaining[k]
            next_values = remaining[k + 1 : k + 1 + column_width]
            if len(next_values) == column_width and all(_is_number_cell(value) for _, value in next_values):
                values_line_range = _line_locator(physical_index + 1, next_values[-1][0] + 1)
                row_path = [*section_stack, label]
                for col, (value_line, value) in enumerate(next_values):
                    period = date_groups[col][1]
                    unit = explicit_unit or _unit_from_header_or_value(f"{label} {value}")
                    context: dict[str, object] = {
                        "table_contract": "generic-table/1.0",
                        "table_identity": title,
                        "table_title": title,
                        "table_signature": _normalized(title),
                        "source_section": " / ".join(section_stack) if section_stack else title,
                        "row_label": label,
                        "row_path": row_path,
                        "column_header_path": [*section_stack, period],
                        "period": period,
                        "statistic": current_statistic,
                        "unit": unit,
                        "value": value,
                        "header_locator": header_locator,
                        "cell_locator": _line_locator(value_line + 1, value_line + 1),
                        "row_locator": values_line_range,
                        "header_excerpt": header_excerpt,
                    }
                    row_text = "\n".join([label, *(cell for _, cell in next_values)])
                    output.append({
                        "source_id": document.source_id,
                        "evidence_text": row_text,
                        "source_section": context["source_section"],
                        "paragraph_locator": f"{values_line_range}; header={header_locator}",
                        "published_at": document.published_at,
                        "retrieved_at": document.retrieved_at,
                        "original_url": document.original_url or document.url,
                        "relation": "supports",
                        "claim_type": "fact",
                        "claim_key": "generic-table|" + "|".join((_normalized(title), _normalized(" / ".join(row_path)), _normalized(period))),
                        "claim_values": [value],
                        "document_hash": document.document_hash,
                        "document_format": document.document_format,
                        "evidence_origin": "original_document",
                        "table_context": context,
                    })
                k += column_width + 1
                continue
            if label.isupper() or (label.startswith("(") and label.endswith(")")):
                if label.startswith("(") and label.endswith(")"):
                    current_statistic = label[1:-1].strip()
                    local_unit = _find_unit([label])
                    if local_unit:
                        explicit_unit = local_unit
                else:
                    section_stack = [label]
                    current_statistic = None
            elif label and re.search(r"[A-Za-z\u0080-\uffff]", label):
                # Non-numeric group labels become explicit row-path context.
                section_stack = [*section_stack[-2:], label]
            k += 1
    return output


def extract_generic_table_evidence(document: FetchedDocument) -> list[dict[str, object]]:
    """Extract only unambiguous exact cells from pipe or line-oriented tables."""
    lines = document.text.splitlines()
    output: list[dict[str, object]] = []
    titles = [(index, line.strip()) for index, line in enumerate(lines) if _TABLE_TITLE.match(line.strip())]
    for title_index, title in titles:
        output.extend(_pipe_table_rows(document, lines, title_index + 1, title))
    output.extend(_line_cell_tables(document))
    deduped: dict[tuple[str, str, str], dict[str, object]] = {}
    for item in output:
        context = item["table_context"]
        key = (str(item["source_id"]), str(item["paragraph_locator"]), str(context["period"]))
        deduped[key] = item
    return list(deduped.values())


def extract_targeted_evidence(
    documents: list[FetchedDocument],
    targets: EvidenceTargetSetV1 | Mapping[str, object],
    *,
    document_roles: Mapping[str, str],
    target_set_sha256: str | None = None,
) -> list[dict[str, object]]:
    """Find exact narrative/table candidates for explicit case targets.

    No fact values are synthesized from a target. Narrative output contains
    only verbatim complete contiguous spans. Table output is accepted only
    when every cell and header column can be mapped without an ambiguous width.
    """
    parsed = targets if isinstance(targets, EvidenceTargetSetV1) else EvidenceTargetSetV1.model_validate(targets)
    output: list[dict[str, object]] = []
    for document in documents:
        role = document_roles.get(document.source_id)
        if not isinstance(role, str):
            continue
        for target in parsed.targets:
            if role not in target.source_roles:
                continue
            seen: set[tuple[str, str, int, int]] = set()
            for locator, excerpt, source_section, source_section_locator in _paragraph_spans(document.text):
                if target.required_source_section is not None and _normalized(
                    (source_section or "").strip()
                ) != _normalized(target.required_source_section):
                    continue
                for proposition_span in atomic_proposition_spans(excerpt):
                    proposition = str(proposition_span["text"])
                    if not _matches_target_alias(target, proposition):
                        continue
                    matched_periods = _period_matches(target, proposition)
                    if not matched_periods:
                        continue
                    explicit_values = _explicit_values(proposition)
                    if target.expected_unit_family is not None and not any(
                        _unit_matches(target.expected_unit_family, value.get("unit"))
                        for value in explicit_values
                    ):
                        continue
                    revision = _revision_values(proposition)
                    kind = "revision" if revision is not None else "narrative_sentence"
                    if kind not in target.evidence_kinds:
                        continue
                    key = (locator, kind, int(proposition_span["start"]), int(proposition_span["end"]))
                    if key in seen:
                        continue
                    seen.add(key)
                    revision_values = _revision_values(proposition, period=matched_periods[0]) if kind == "revision" else None
                    output.append(_targeted_record(
                        document,
                        target,
                        evidence_text=excerpt,
                        proposition_span=proposition_span,
                        locator=locator,
                        kind=kind,
                        period_matches=matched_periods,
                        target_set_sha256=target_set_sha256,
                        revision_values=revision_values,
                        source_section=source_section,
                        source_section_locator=source_section_locator,
                    ))
            if "table_cell" in target.evidence_kinds:
                for candidate in extract_generic_table_evidence(document):
                    context = candidate["table_context"]
                    if target.required_source_section is not None and _normalized(
                        target.required_source_section
                    ) not in {
                        _normalized(str(context.get("source_section", ""))),
                        _normalized(str(context.get("table_title", ""))),
                    }:
                        continue
                    text_for_match = " ".join([
                        str(context.get("row_label", "")),
                        " ".join(str(part) for part in context.get("row_path", [])),
                        " ".join(str(part) for part in context.get("column_header_path", [])),
                    ])
                    if not _matches_target_alias(target, text_for_match):
                        continue
                    matched_periods = _period_matches(target, str(context.get("period", "")))
                    if not matched_periods:
                        continue
                    if target.expected_unit_family is not None and not _unit_matches(
                        target.expected_unit_family, context.get("unit")
                    ):
                        continue
                    locator = str(candidate["paragraph_locator"])
                    raw_text = str(candidate["evidence_text"])
                    table_value = str(context.get("value", ""))
                    value_positions = [match.start() for match in re.finditer(re.escape(table_value), raw_text)] if table_value else []
                    if len(value_positions) != 1:
                        # Repeated values in one row do not identify a unique
                        # column proposition, so this candidate remains unusable.
                        continue
                    value_start = value_positions[0]
                    proposition_span = {
                        "start": value_start,
                        "end": value_start + len(table_value),
                        "text": table_value,
                    }
                    key = (locator, "table_cell", value_start, value_start + len(table_value))
                    if key in seen:
                        continue
                    seen.add(key)
                    output.append(_targeted_record(
                        document,
                        target,
                        evidence_text=raw_text,
                        proposition_span=proposition_span,
                        locator=locator,
                        kind="table_cell",
                        period_matches=matched_periods,
                        table_context=dict(context),
                        target_set_sha256=target_set_sha256,
                    ))
    return output


def _unit_matches(expected: str, actual: object) -> bool:
    if not isinstance(actual, str):
        return False
    aliases = {
        "currency": {"$", "dollars", "euros", "pounds"},
        "count": {"jobs", "workers", "employees", "persons", "people", "thousands", "millions"},
        "percent": {"percent", "percentage", "percentage point", "percentage points"},
        "hours": {"hour", "hours"},
        "index": {"index point", "index points"},
    }
    folded_expected = _normalized(expected)
    folded_actual = _normalized(actual)
    if folded_expected in aliases:
        return folded_actual in aliases[folded_expected]
    return folded_expected == folded_actual


def build_authority_claim_proposals(
    evidence: list[dict[str, object]],
    targets: EvidenceTargetSetV1,
    *,
    institution_display_name: str,
) -> dict[str, dict[str, object]]:
    """Build exact-quotation proposals; the existing authority verifier decides eligibility."""
    if not institution_display_name.strip():
        raise ValueError("institution_display_name must not be blank")
    from fanglei.research import evidence_claim_key

    target_by_id = {target.target_id: target for target in targets.targets}
    proposals: dict[str, dict[str, object]] = {}
    for item in evidence:
        target = target_by_id.get(str(item.get("evidence_target_id")))
        excerpt = item.get("evidence_text")
        source_id = item.get("source_id")
        if (
            target is None
            or not isinstance(excerpt, str)
            or not excerpt
            or not isinstance(source_id, str)
            or item.get("evidence_eligible") is not True
        ):
            continue
        key = evidence_claim_key(item)
        if key in proposals:
            # A target must not turn several spans into one ambiguous quote.
            raise ValueError(f"multiple evidence candidates share target claim key: {key}")
        proposition_span = item.get("proposition_span")
        if validate_proposition_span(excerpt, proposition_span) is None:
            continue
        table_context = item.get("table_context")
        if isinstance(table_context, dict):
            if proposition_span.get("text") != table_context.get("value"):
                continue
            proposition = canonical_table_proposition(
                institution_display_name, target.authority_scope, table_context
            )
        else:
            proposition = f'{institution_display_name}: "{proposition_span["text"]}"'
        proposals[key] = {
            "claim_type": "fact",
            "claim_text": proposition,
            "authority_attestation": {
                "kind": "document_report",
                "source_ids": [source_id],
                "attribution": institution_display_name,
                "scope": target.authority_scope.model_dump(mode="json"),
            },
        }
    return proposals
