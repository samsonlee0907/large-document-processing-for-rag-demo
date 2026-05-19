from __future__ import annotations

import re

from backend.domain.models import IntermediateDocument, SectionNode


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


def normalize_document(document: IntermediateDocument) -> IntermediateDocument:
    document.sections = [_walk_sections(section) for section in document.sections]
    return document
