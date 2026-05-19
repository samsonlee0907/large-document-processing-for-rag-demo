from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Stage(str, Enum):
    uploaded = "uploaded"
    parsing = "parsing"
    extraction = "ocr_layout_extraction"
    cleanup = "cleanup_normalization"
    chunking = "chunking"
    enrichment = "metadata_enrichment"
    embedding = "embedding_index_preparation"
    publishing = "publishing_syncing"
    ready = "ready_for_chat"
    failed = "failed"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class PipelineMessage(BaseModel):
    timestamp: str = Field(default_factory=utc_now)
    level: str = "info"
    message: str


class SectionNode(BaseModel):
    heading: str
    level: int = 1
    page_start: int | None = None
    page_end: int | None = None
    paragraphs: list[str] = Field(default_factory=list)
    tables: list[list[list[str]]] = Field(default_factory=list)
    children: list["SectionNode"] = Field(default_factory=list)


SectionNode.model_rebuild()


class IntermediateDocument(BaseModel):
    doc_id: str
    source_name: str
    source_path: str
    source_uri: str | None = None
    format: str
    complexity: str
    parser_path: str
    page_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: list[SectionNode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChunkRecord(BaseModel):
    chunk_id: str
    doc_id: str
    source_name: str
    source_uri: str | None = None
    page_numbers: list[int] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)
    content_type: str = "text"
    tags: list[str] = Field(default_factory=list)
    checksum: str
    last_updated: str = Field(default_factory=utc_now)
    clean_text: str
    token_estimate: int
    image_evidence: list[dict[str, Any]] = Field(default_factory=list)


class PublishStatus(BaseModel):
    mode: str
    resource: str
    ready: bool = False
    last_sync_time: str | None = None
    indexed_document_count: int = 0
    indexed_chunk_count: int = 0
    message: str = ""
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    doc_id: str = Field(default_factory=lambda: uuid4().hex)
    file_name: str
    stored_path: str
    format: str = "unknown"
    complexity: str = "unknown"
    page_count: int | None = None
    parser_path: str = "pending"
    stage: Stage = Stage.uploaded
    status: JobStatus = JobStatus.queued
    progress: int = 0
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    activity: list[PipelineMessage] = Field(default_factory=list)
    chunk_count: int = 0
    section_count: int = 0
    intermediate_path: str | None = None
    chunks_path: str | None = None
    publish_status: PublishStatus = Field(
        default_factory=lambda: PublishStatus(
            mode="not_configured",
            resource="Azure AI Search Knowledge Base",
            ready=False,
            message="Azure AI Search is not configured.",
        )
    )

    def touch(self) -> None:
        self.updated_at = utc_now()


class JobStoreModel(BaseModel):
    jobs: list[JobRecord] = Field(default_factory=list)


class ChatTurnRequest(BaseModel):
    question: str
    knowledge_base: str | None = None
    corpus_mode: str = "auto"
    corpus_doc_ids: list[str] = Field(default_factory=list)
    include_debug: bool = False


class ChatCitation(BaseModel):
    title: str
    uri: str | None = None
    chunk_id: str | None = None
    doc_id: str | None = None
    page_numbers: list[int] = Field(default_factory=list)
    snippet: str = ""
    image_evidence: list[dict[str, Any]] = Field(default_factory=list)


class ChatTurnResponse(BaseModel):
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
