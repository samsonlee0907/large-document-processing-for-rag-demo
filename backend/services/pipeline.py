from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from fastapi import BackgroundTasks, UploadFile

from backend.core.config import settings
from backend.domain.models import ChunkRecord, IntermediateDocument, JobRecord, JobStatus, PipelineMessage, Stage
from backend.services.chunking import ChunkPolicy, StructureAwareChunker
from backend.services.indexing import build_foundry_adapter
from backend.services.job_store import job_store
from backend.services.normalization import normalize_document
from backend.services.parsers import parser_registry

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self) -> None:
        self.chunker = StructureAwareChunker(
            ChunkPolicy(
                chunk_size_tokens=settings.chunk_size_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
                semantic_mode=settings.use_semantic_chunking,
            )
        )

    async def create_job(self, file: UploadFile, background_tasks: BackgroundTasks) -> JobRecord:
        file_name = file.filename or "upload.bin"
        temp_record = JobRecord(file_name=file_name, stored_path="")
        stored_path = settings.uploads_dir / f"{temp_record.doc_id}_{file_name}"
        with stored_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        return self.create_job_from_path(
            stored_path,
            background_tasks,
            doc_id=temp_record.doc_id,
            file_name=file_name,
            activity_message="File uploaded and queued for ingestion.",
        )

    def create_job_from_path(
        self,
        path: Path,
        background_tasks: BackgroundTasks,
        *,
        doc_id: str | None = None,
        file_name: str | None = None,
        activity_message: str = "Document queued for ingestion.",
    ) -> JobRecord:
        resolved_file_name = file_name or path.name
        temp_record = JobRecord(file_name=resolved_file_name, stored_path="")
        resolved_doc_id = doc_id or temp_record.doc_id
        profile = parser_registry.detect(path)
        job = JobRecord(
            doc_id=resolved_doc_id,
            file_name=resolved_file_name,
            stored_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            page_count=profile.page_count,
            parser_path=profile.parser_path,
            warnings=profile.warnings,
            activity=[],
            status=JobStatus.queued,
            progress=5,
            stage=Stage.uploaded,
        )
        job.activity.append(
            PipelineMessage(
                timestamp=job.created_at,
                level="info",
                message=activity_message,
            )
        )
        job_store.upsert(job)
        background_tasks.add_task(self.run, job.doc_id)
        return job

    def retry(self, doc_id: str, background_tasks: BackgroundTasks) -> JobRecord:
        job = job_store.get(doc_id)

        def mutate(current: JobRecord) -> None:
            current.status = JobStatus.queued
            current.stage = Stage.uploaded
            current.progress = 5
            current.errors = []
            current.activity.append(
                PipelineMessage(timestamp=current.updated_at, level="info", message="Retry requested.")
            )

        updated = job_store.mutate(doc_id, mutate)
        background_tasks.add_task(self.run, job.doc_id)
        return updated

    def run(self, doc_id: str) -> None:
        try:
            job = job_store.get(doc_id)
            path = Path(job.stored_path)

            job_store.mark_stage(doc_id, Stage.parsing, 15, "Selecting parser path and validating document.")
            profile = parser_registry.detect(path)
            intermediate = parser_registry.parse(path, doc_id, profile)
            job_store.mark_stage(
                doc_id,
                Stage.extraction,
                30,
                f"Extraction completed via {intermediate.parser_path}.",
                parser_path=intermediate.parser_path,
            )

            intermediate = normalize_document(intermediate)
            job_store.mark_stage(doc_id, Stage.cleanup, 45, "Normalized whitespace and preserved section structure.")

            chunks = self.chunker.chunk(intermediate)
            job_store.mark_stage(
                doc_id,
                Stage.chunking,
                60,
                f"Generated {len(chunks)} retrieval-friendly chunks.",
            )

            enriched_chunks = self._enrich_chunks(intermediate, chunks)
            job_store.mark_stage(doc_id, Stage.enrichment, 72, "Chunk metadata enriched for filtering and citation.")
            job_store.mark_stage(doc_id, Stage.embedding, 82, "Prepared chunks for Azure AI Search publishing.")

            intermediate_path = settings.artifacts_dir / f"{doc_id}_intermediate.json"
            chunks_path = settings.artifacts_dir / f"{doc_id}_chunks.json"
            intermediate_path.write_text(intermediate.model_dump_json(indent=2), encoding="utf-8")
            chunks_path.write_text(
                json.dumps([chunk.model_dump(mode="json") for chunk in enriched_chunks], indent=2),
                encoding="utf-8",
            )
            job_store.mutate(
                doc_id,
                lambda current: self._store_artifact_metadata(current, intermediate, enriched_chunks, intermediate_path, chunks_path),
            )

            adapter = build_foundry_adapter()
            publish_status = adapter.publish(enriched_chunks)
            job_store.update_publish_status(doc_id, publish_status)
            job_store.mark_stage(doc_id, Stage.publishing, 92, publish_status.message)

            job_store.mark_stage(doc_id, Stage.ready, 100, "Document is ready for chat.")
        except Exception as exc:  # pragma: no cover - production behavior
            logger.exception("pipeline failed", extra={"context": {"doc_id": doc_id}})

            def mutate(current: JobRecord) -> None:
                current.status = JobStatus.failed
                current.stage = Stage.failed
                current.errors.append(str(exc))
                current.activity.append(
                    PipelineMessage(timestamp=current.updated_at, level="error", message=str(exc))
                )

            job_store.mutate(doc_id, mutate)

    def _enrich_chunks(self, intermediate: IntermediateDocument, chunks: list[ChunkRecord]) -> list[ChunkRecord]:
        figure_artifacts = intermediate.metadata.get("figure_artifacts") or []
        for chunk in chunks:
            if intermediate.page_count and not chunk.page_numbers:
                chunk.page_numbers = [1]
            if intermediate.metadata:
                chunk.tags.extend(
                    [value for value in [intermediate.metadata.get("model_id"), intermediate.metadata.get("analyzer_id")] if value]
                )
            if figure_artifacts:
                related_figures = []
                for figure in figure_artifacts:
                    if not isinstance(figure, dict):
                        continue
                    page_number = figure.get("page_number")
                    if page_number is None or not chunk.page_numbers or page_number in chunk.page_numbers:
                        related_figures.append(figure)
                chunk.image_evidence = related_figures[:4]
        return chunks

    def _store_artifact_metadata(
        self,
        job: JobRecord,
        intermediate: IntermediateDocument,
        chunks: list[ChunkRecord],
        intermediate_path: Path,
        chunks_path: Path,
    ) -> None:
        job.format = intermediate.format
        job.complexity = intermediate.complexity
        job.page_count = intermediate.page_count
        job.parser_path = intermediate.parser_path
        job.section_count = len(intermediate.sections)
        job.chunk_count = len(chunks)
        job.intermediate_path = str(intermediate_path)
        job.chunks_path = str(chunks_path)
        for warning in intermediate.warnings:
            if warning not in job.warnings:
                job.warnings.append(warning)


pipeline = IngestionPipeline()
