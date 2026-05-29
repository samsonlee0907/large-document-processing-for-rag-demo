from __future__ import annotations

import re

from backend.core.config import settings
from backend.domain.models import IntermediateDocument, SectionNode
from backend.services.foundry_openai import stitch_segment_boundary_with_foundry

GENERIC_SEGMENT_HEADING = re.compile(r"^Pages\s+\d+\s*-\s*\d+$", re.IGNORECASE)
STRONG_TERMINAL_PATTERN = re.compile(r"""[.!?]["')\]]*$""")
CONTINUATION_PREFIXES = (
    "and ",
    "or ",
    "but ",
    "which ",
    "that ",
    "who ",
    "where ",
    "when ",
    "because ",
    "including ",
    "using ",
    "into ",
    "to ",
    "for ",
    "with ",
    "while ",
    "as ",
    "than ",
    "from ",
)


def _normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _walk_sections(section: SectionNode) -> SectionNode:
    section.heading = _normalize_text(section.heading) or "Untitled Section"
    section.paragraphs = [_normalize_text(paragraph) for paragraph in section.paragraphs if _normalize_text(paragraph)]
    section.children = [_walk_sections(child) for child in section.children]
    return section


def _normalized_fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _is_generic_heading(heading: str) -> bool:
    normalized = _normalize_text(heading)
    return bool(normalized and GENERIC_SEGMENT_HEADING.match(normalized))


def _is_special_section(section: SectionNode) -> bool:
    return section.heading.strip().lower() == "extracted figures"


def _has_strong_terminal(text: str) -> bool:
    return bool(STRONG_TERMINAL_PATTERN.search(text.strip()))


def _starts_like_continuation(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    first = stripped[0]
    if first.islower():
        return True
    if first in ",;:)]}%":
        return True
    lowered = stripped.lower()
    return lowered.startswith(CONTINUATION_PREFIXES)


def _merge_paragraph_text(previous_text: str, next_text: str) -> str:
    left = previous_text.rstrip()
    right = next_text.lstrip()
    if not left:
        return right
    if not right:
        return left
    if left.endswith("-") and right[:1].isalnum():
        return f"{left[:-1]}{right}"
    if left[-1] in "([{\"'/" or right[0] in ",.;:!?)]}%":
        return f"{left}{right}"
    return f"{left} {right}"


def _section_page_min(section: SectionNode) -> int | None:
    candidates = [value for value in [section.page_start, section.page_end] if value is not None]
    for child in section.children:
        child_min = _section_page_min(child)
        if child_min is not None:
            candidates.append(child_min)
    return min(candidates) if candidates else None


def _section_page_max(section: SectionNode) -> int | None:
    candidates = [value for value in [section.page_start, section.page_end] if value is not None]
    for child in section.children:
        child_max = _section_page_max(child)
        if child_max is not None:
            candidates.append(child_max)
    return max(candidates) if candidates else None


def _update_page_range(section: SectionNode, *, page_start: int | None, page_end: int | None) -> None:
    values_start = [value for value in [section.page_start, page_start] if value is not None]
    values_end = [value for value in [section.page_end, page_end] if value is not None]
    section.page_start = min(values_start) if values_start else None
    section.page_end = max(values_end) if values_end else None


def _boundary_merge_score(previous_section: SectionNode, next_section: SectionNode) -> int:
    if not previous_section.paragraphs or not next_section.paragraphs:
        return 0
    previous_text = previous_section.paragraphs[-1]
    next_text = next_section.paragraphs[0]
    score = 0
    if previous_text.rstrip().endswith("-"):
        return 100
    if not _has_strong_terminal(previous_text):
        score += 2
    if previous_text.rstrip().endswith((",", ";", ":", "(", "[", "{", "/")):
        score += 1
    if _starts_like_continuation(next_text):
        score += 2
    if previous_section.heading == next_section.heading:
        score += 2
    elif _is_generic_heading(previous_section.heading) or _is_generic_heading(next_section.heading):
        score += 1
    return score


def _llm_boundary_merge(previous_section: SectionNode, next_section: SectionNode) -> str | None:
    if not settings.enable_llm_boundary_stitching or not settings.azure_foundry_chat_enabled:
        return None
    if not previous_section.paragraphs or not next_section.paragraphs:
        return None
    try:
        return stitch_segment_boundary_with_foundry(
            previous_section.paragraphs[-1],
            next_section.paragraphs[0],
            previous_heading=previous_section.heading,
            next_heading=next_section.heading,
        )
    except Exception:
        return None


def _merge_sections(target: SectionNode, source: SectionNode) -> SectionNode:
    target.paragraphs.extend(source.paragraphs)
    target.tables.extend(source.tables)
    target.children.extend(source.children)
    _update_page_range(
        target,
        page_start=_section_page_min(source),
        page_end=_section_page_max(source),
    )
    return target


def _is_effectively_empty(section: SectionNode) -> bool:
    return not section.paragraphs and not section.tables and not section.children


def _stitch_segment_boundaries(document: IntermediateDocument) -> IntermediateDocument:
    if document.metadata.get("segmentation_strategy") != "pdf_page_segmentation":
        return document
    if len(document.sections) < 2:
        return document

    merged_sections: list[SectionNode] = []
    current = document.sections[0]
    stats = {
        "applied": True,
        "heuristic_merges": 0,
        "llm_merges": 0,
        "deduped_paragraphs": 0,
        "merged_sections": 0,
    }

    for next_section in document.sections[1:]:
        if _is_special_section(current) or _is_special_section(next_section):
            if not _is_effectively_empty(current):
                merged_sections.append(current)
            current = next_section
            continue

        merged_boundary = False
        used_llm = False
        if current.paragraphs and next_section.paragraphs:
            previous_text = current.paragraphs[-1]
            next_text = next_section.paragraphs[0]

            if _normalized_fingerprint(previous_text) == _normalized_fingerprint(next_text):
                next_section.paragraphs.pop(0)
                stats["deduped_paragraphs"] += 1
            else:
                score = _boundary_merge_score(current, next_section)
                merged_text: str | None = None
                if score >= 4:
                    merged_text = _merge_paragraph_text(previous_text, next_text)
                elif score >= 2:
                    merged_text = _llm_boundary_merge(current, next_section)
                    used_llm = merged_text is not None
                    if merged_text is None and (
                        not _has_strong_terminal(previous_text) or _starts_like_continuation(next_text)
                    ):
                        merged_text = _merge_paragraph_text(previous_text, next_text)
                if merged_text:
                    current.paragraphs[-1] = _normalize_text(merged_text)
                    next_section.paragraphs.pop(0)
                    _update_page_range(
                        current,
                        page_start=next_section.page_start,
                        page_end=next_section.page_start or next_section.page_end,
                    )
                    merged_boundary = True
                    if used_llm:
                        stats["llm_merges"] += 1
                    else:
                        stats["heuristic_merges"] += 1

        should_merge_sections = (
            current.heading == next_section.heading
            or (_is_generic_heading(current.heading) and _is_generic_heading(next_section.heading))
            or (merged_boundary and _is_generic_heading(next_section.heading))
        )
        if should_merge_sections:
            current = _merge_sections(current, next_section)
            stats["merged_sections"] += 1
            continue

        if not _is_effectively_empty(current):
            merged_sections.append(current)
        current = next_section

    if not _is_effectively_empty(current):
        merged_sections.append(current)

    document.sections = merged_sections
    document.metadata["boundary_stitch"] = stats
    return document


def normalize_document(document: IntermediateDocument) -> IntermediateDocument:
    document.sections = [_walk_sections(section) for section in document.sections]
    document = _stitch_segment_boundaries(document)
    document.sections = [_walk_sections(section) for section in document.sections]
    return document
