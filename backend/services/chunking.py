from __future__ import annotations

import hashlib
from dataclasses import dataclass

from backend.core.config import settings
from backend.domain.models import ChunkRecord, IntermediateDocument, SectionNode


def _token_estimate(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass(slots=True)
class ChunkPolicy:
    name: str = "structure_recursive"
    chunk_size_tokens: int = settings.chunk_size_tokens
    overlap_tokens: int = settings.chunk_overlap_tokens
    semantic_mode: bool = settings.use_semantic_chunking


class StructureAwareChunker:
    def __init__(self, policy: ChunkPolicy | None = None) -> None:
        self.policy = policy or ChunkPolicy()

    def chunk(self, document: IntermediateDocument) -> list[ChunkRecord]:
        chunks: list[ChunkRecord] = []
        counter = 0
        for section in document.sections:
            counter = self._walk(
                document=document,
                section=section,
                heading_path=[],
                chunks=chunks,
                counter=counter,
            )
        if not chunks:
            chunks.append(
                self._build_chunk(
                    document=document,
                    counter=0,
                    section_path=["Document"],
                    text=f"{document.source_name}\n\nNo extractable content was produced.",
                    page_numbers=[],
                )
            )
        return chunks

    def _walk(
        self,
        document: IntermediateDocument,
        section: SectionNode,
        heading_path: list[str],
        chunks: list[ChunkRecord],
        counter: int,
    ) -> int:
        path = [*heading_path, section.heading]
        buffers = list(section.paragraphs)
        if section.tables:
            for table in section.tables:
                table_lines = [" | ".join(row) for row in table if row]
                if table_lines:
                    buffers.append("\n".join(table_lines))

        joined = "\n\n".join(part for part in buffers if part.strip())
        if joined.strip():
            counter = self._emit_segmented_chunks(document, chunks, counter, path, joined, section)

        for child in section.children:
            counter = self._walk(document, child, path, chunks, counter)
        return counter

    def _emit_segmented_chunks(
        self,
        document: IntermediateDocument,
        chunks: list[ChunkRecord],
        counter: int,
        section_path: list[str],
        text: str,
        section: SectionNode,
    ) -> int:
        words = text.split()
        target_words = max(60, self.policy.chunk_size_tokens)
        overlap_words = min(self.policy.overlap_tokens, max(0, target_words // 3))
        start = 0
        while start < len(words):
            end = min(len(words), start + target_words)
            segment = " ".join(words[start:end]).strip()
            if segment:
                counter += 1
                page_numbers = []
                if section.page_start is not None:
                    if section.page_end is not None:
                        page_numbers = list(range(section.page_start, section.page_end + 1))
                    else:
                        page_numbers = [section.page_start]
                chunks.append(
                    self._build_chunk(document, counter, section_path, segment, page_numbers)
                )
            if end >= len(words):
                break
            start = max(0, end - overlap_words)
        return counter

    def _build_chunk(
        self,
        document: IntermediateDocument,
        counter: int,
        section_path: list[str],
        text: str,
        page_numbers: list[int],
    ) -> ChunkRecord:
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ChunkRecord(
            chunk_id=f"{document.doc_id}-chunk-{counter:04d}",
            doc_id=document.doc_id,
            source_name=document.source_name,
            source_uri=document.source_uri,
            page_numbers=page_numbers,
            section_path=section_path,
            checksum=checksum,
            clean_text=text,
            token_estimate=_token_estimate(text),
            tags=[document.format, document.complexity, self.policy.name],
        )
