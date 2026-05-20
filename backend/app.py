from __future__ import annotations

import json
from pathlib import Path
import shutil

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.core.config import settings
from backend.core.logging import configure_logging
from backend.domain.models import ChatTurnRequest, ChatTurnResponse, JobRecord, PublishStatus
from backend.services.blob_storage import build_blob_artifact_store
from backend.services.chat import local_preview_chat, synthesize_grounded_chat
from backend.services.indexing import LocalPreviewAdapter, build_foundry_adapter
from backend.services.job_store import job_store
from backend.services.pipeline import pipeline
from backend.services.sample_documents import (
    create_construction_industry_report,
    create_generative_ai_futures_report,
    create_random_research_corpus,
)

configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path.cwd() / "frontend" / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _job_or_404(doc_id: str) -> JobRecord:
    try:
        return job_store.get(doc_id)
    except KeyError as exc:  # pragma: no cover - API handling
        raise HTTPException(status_code=404, detail="Document not found.") from exc


def _load_chunk_records(job: JobRecord) -> list:
    if not job.chunks_path or not Path(job.chunks_path).exists():
        return []
    from backend.domain.models import ChunkRecord

    payload = json.loads(Path(job.chunks_path).read_text(encoding="utf-8"))
    return [ChunkRecord.model_validate(item) for item in payload]


def _job_route_text(job: JobRecord) -> str:
    if not job.intermediate_path or not Path(job.intermediate_path).exists():
        return ""
    try:
        intermediate = json.loads(Path(job.intermediate_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    headings = []
    for section in intermediate.get("sections") or []:
        if not isinstance(section, dict):
            continue
        heading = section.get("heading")
        if isinstance(heading, str) and heading.strip():
            headings.append(heading.strip())
        if len(headings) >= 12:
            break
    return " ".join(headings)


def _delete_job_artifacts(job: JobRecord) -> None:
    intermediate_payload = None
    if job.intermediate_path and Path(job.intermediate_path).exists():
        intermediate_payload = json.loads(Path(job.intermediate_path).read_text(encoding="utf-8"))

    directory_candidates = []
    stored_path = Path(job.stored_path)
    directory_candidates.append(settings.artifacts_dir / f"{job.doc_id}_figures")
    directory_candidates.append(settings.artifacts_dir / f"{stored_path.stem}_segments")
    directory_candidates.append(settings.artifacts_dir / f"{stored_path.stem}_diagrams")
    for directory in directory_candidates:
        if directory.exists() and directory.is_dir():
            shutil.rmtree(directory, ignore_errors=True)

    if intermediate_payload:
        figures = (intermediate_payload.get("metadata") or {}).get("figure_artifacts") or []
        blob_store = build_blob_artifact_store()
        if blob_store is not None:
            for figure in figures:
                if not isinstance(figure, dict):
                    continue
                blob_name = figure.get("blob_name")
                if not blob_name:
                    continue
                try:
                    blob_store.delete_blob(blob_name)
                except Exception:
                    continue

    paths_to_unlink = [
        job.stored_path,
        job.intermediate_path,
        job.chunks_path,
    ]
    for raw_path in paths_to_unlink:
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.exists() and path.is_file():
            path.unlink()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config_summary() -> dict[str, object]:
    return {
        "app_name": settings.app_name,
        "azure_document_intelligence_enabled": settings.azure_docint_enabled,
        "azure_content_understanding_enabled": settings.azure_content_understanding_enabled,
        "azure_search_enabled": settings.azure_search_enabled,
        "azure_agentic_retrieval_enabled": settings.azure_search_enabled,
        "azure_agentic_planning_model_enabled": settings.azure_search_llm_enabled,
        "azure_agentic_planning_model": settings.azure_search_llm_deployment,
        "azure_search_multi_index_enabled": settings.azure_search_multi_index_enabled,
        "azure_search_extra_indexes": [source.index_name for source in settings.azure_search_extra_sources],
        "azure_blob_storage_enabled": settings.azure_blob_storage_enabled,
        "foundry_chat_mode": settings.foundry_chat_mode,
        "knowledge_base_name": settings.azure_search_knowledge_base_name,
        "search_index_name": settings.azure_search_index_name,
    }


@app.get("/api/dashboard")
def dashboard() -> dict[str, object]:
    jobs = job_store.list_jobs()
    return {
        "total_documents": len(jobs),
        "processing_queue": len([job for job in jobs if job.status == "processing"]),
        "ready_for_chat": len([job for job in jobs if job.status == "ready"]),
        "failed_jobs": len([job for job in jobs if job.status == "failed"]),
        "recent_activity": [
            {"doc_id": job.doc_id, "file_name": job.file_name, "stage": job.stage, "updated_at": job.updated_at}
            for job in sorted(jobs, key=lambda item: item.updated_at, reverse=True)[:8]
        ],
    }


@app.get("/api/documents")
def list_documents() -> list[dict[str, object]]:
    return [job.model_dump(mode="json") for job in sorted(job_store.list_jobs(), key=lambda item: item.created_at, reverse=True)]


@app.post("/api/documents/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict[str, object]:
    job = await pipeline.create_job(file, background_tasks)
    return job.model_dump(mode="json")


@app.post("/api/samples/random-research-corpus")
def create_random_research_sample(
    background_tasks: BackgroundTasks,
    page_count: int = settings.hard_page_split_threshold + 5,
    topic: str | None = None,
) -> dict[str, object]:
    if page_count <= settings.hard_page_split_threshold:
        raise HTTPException(
            status_code=400,
            detail=(
                f"page_count must be greater than the hard split threshold of "
                f"{settings.hard_page_split_threshold}."
            ),
        )
    sample = create_random_research_corpus(page_count=page_count, topic=topic)
    job = pipeline.create_job_from_path(
        sample.path,
        background_tasks,
        file_name=sample.file_name,
        activity_message=(
            f"Generated {sample.page_count}-page research corpus on {sample.report_title or 'a random topic'} and queued it for segmented ingestion."
        ),
    )
    return {
        "job": job.model_dump(mode="json"),
        "sample": {
            "file_name": sample.file_name,
            "page_count": sample.page_count,
            "path": str(sample.path),
            "section_interval": sample.section_interval,
            "topic_key": sample.topic_key,
            "report_title": sample.report_title,
        },
    }


@app.post("/api/samples/generative-ai-futures-report")
def create_generative_ai_futures_sample(
    background_tasks: BackgroundTasks, page_count: int = 520
) -> dict[str, object]:
    if page_count <= 500:
        raise HTTPException(status_code=400, detail="page_count must be greater than 500.")
    sample = create_generative_ai_futures_report(page_count=page_count)
    job = pipeline.create_job_from_path(
        sample.path,
        background_tasks,
        file_name=sample.file_name,
        activity_message=(
            f"Generated {sample.page_count}-page futures report with diagrams and queued it for ingestion."
        ),
    )
    return {
        "job": job.model_dump(mode="json"),
        "sample": {
            "file_name": sample.file_name,
            "page_count": sample.page_count,
            "path": str(sample.path),
            "section_interval": sample.section_interval,
        },
    }


@app.post("/api/samples/construction-industry-report")
def create_construction_industry_sample(
    background_tasks: BackgroundTasks, page_count: int = 540
) -> dict[str, object]:
    if page_count <= 500:
        raise HTTPException(status_code=400, detail="page_count must be greater than 500.")
    sample = create_construction_industry_report(page_count=page_count)
    job = pipeline.create_job_from_path(
        sample.path,
        background_tasks,
        file_name=sample.file_name,
        activity_message=(
            f"Generated {sample.page_count}-page construction report with architecture diagrams and queued it for ingestion."
        ),
    )
    return {
        "job": job.model_dump(mode="json"),
        "sample": {
            "file_name": sample.file_name,
            "page_count": sample.page_count,
            "path": str(sample.path),
            "section_interval": sample.section_interval,
        },
    }


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str) -> dict[str, object]:
    job = _job_or_404(doc_id)
    payload = job.model_dump(mode="json")
    if job.intermediate_path and Path(job.intermediate_path).exists():
        payload["intermediate"] = json.loads(Path(job.intermediate_path).read_text(encoding="utf-8"))
    if job.chunks_path and Path(job.chunks_path).exists():
        payload["chunks"] = json.loads(Path(job.chunks_path).read_text(encoding="utf-8"))
    return payload


@app.get("/api/documents/{doc_id}/figures/{artifact_id}")
def get_document_figure(doc_id: str, artifact_id: str) -> Response:
    job = _job_or_404(doc_id)
    if not job.intermediate_path or not Path(job.intermediate_path).exists():
        raise HTTPException(status_code=404, detail="No intermediate artifact is available for this document.")
    intermediate = json.loads(Path(job.intermediate_path).read_text(encoding="utf-8"))
    metadata = intermediate.get("metadata") or {}
    figures = metadata.get("figure_artifacts") or []
    figure = next(
        (
            item
            for item in figures
            if isinstance(item, dict) and item.get("artifact_id") == artifact_id
        ),
        None,
    )
    if not figure:
        raise HTTPException(status_code=404, detail="Figure artifact not found.")

    blob_name = figure.get("blob_name")
    if blob_name and settings.azure_blob_storage_enabled:
        blob_store = build_blob_artifact_store()
        if blob_store is not None:
            content, content_type = blob_store.download_bytes(blob_name)
            return Response(content=content, media_type=content_type)

    artifact_path = figure.get("artifact_path")
    if artifact_path and Path(artifact_path).exists():
        return FileResponse(artifact_path)
    raise HTTPException(status_code=404, detail="Figure artifact is not available.")


@app.post("/api/documents/{doc_id}/retry")
def retry_document(doc_id: str, background_tasks: BackgroundTasks) -> dict[str, object]:
    _job_or_404(doc_id)
    job = pipeline.retry(doc_id, background_tasks)
    return job.model_dump(mode="json")


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> dict[str, object]:
    job = _job_or_404(doc_id)
    if job.status.value in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="This document is still processing and cannot be deleted yet.")

    adapter = build_foundry_adapter()
    chunks = _load_chunk_records(job)
    try:
        adapter.delete_chunks(
            chunks,
            index_name=(job.publish_status.diagnostics or {}).get("index_name"),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to remove corpus content from Azure AI Search: {exc}") from exc

    _delete_job_artifacts(job)
    job_store.delete(doc_id)
    return {
        "deleted": True,
        "doc_id": doc_id,
        "file_name": job.file_name,
        "removed_chunk_count": len(chunks),
    }


@app.get("/api/knowledge/status")
def knowledge_status() -> dict[str, object]:
    status = build_foundry_adapter().get_status()
    jobs = job_store.list_jobs()
    ready_docs = [job for job in jobs if job.status == "ready"]
    return {
        "selected_knowledge_base": settings.azure_search_knowledge_base_name,
        "status": status.model_dump(mode="json"),
        "documents": [
            {
                "doc_id": job.doc_id,
                "file_name": job.file_name,
                "chunk_count": job.chunk_count,
                "section_count": job.section_count,
                "last_sync_time": job.publish_status.last_sync_time,
            }
            for job in ready_docs
        ],
    }


@app.post("/api/knowledge/sync")
def resync_knowledge() -> dict[str, object]:
    ready_jobs = [job for job in job_store.list_jobs() if job.chunks_path and Path(job.chunks_path).exists()]
    if not ready_jobs:
        raise HTTPException(status_code=400, detail="No processed documents are available to sync.")
    adapter = build_foundry_adapter()
    per_document = []
    latest_status = None
    for job in ready_jobs:
        chunks = _load_chunk_records(job)
        previous_index = (job.publish_status.diagnostics or {}).get("index_name")
        status = adapter.publish(
            chunks,
            source_name=job.file_name,
            route_text=_job_route_text(job),
        )
        latest_status = status
        job_store.update_publish_status(job.doc_id, status)
        new_index = (status.diagnostics or {}).get("index_name")
        if previous_index and new_index and previous_index != new_index:
            adapter.delete_chunks(chunks, index_name=previous_index)
        per_document.append(
            {
                "doc_id": job.doc_id,
                "file_name": job.file_name,
                "index_name": new_index,
                "knowledge_source_name": (status.diagnostics or {}).get("knowledge_source_name"),
            }
        )
    return {
        "status": latest_status.model_dump(mode="json") if latest_status else {},
        "documents": per_document,
    }


@app.post("/api/chat", response_model=ChatTurnResponse)
def chat(request: ChatTurnRequest) -> ChatTurnResponse:
    jobs = [job for job in job_store.list_jobs() if job.status == "ready" and job.chunks_path]
    if not jobs:
        raise HTTPException(status_code=400, detail="No ready corpus is available for chat.")

    selected_doc_ids: list[str] = []
    if request.corpus_mode == "custom":
        selected_doc_ids = [doc_id for doc_id in request.corpus_doc_ids if doc_id]
        if not selected_doc_ids:
            raise HTTPException(status_code=400, detail="Select at least one corpus when using custom mode.")
        ready_ids = {job.doc_id for job in jobs}
        invalid = [doc_id for doc_id in selected_doc_ids if doc_id not in ready_ids]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Some selected corpora are not ready: {', '.join(invalid)}")

    adapter = build_foundry_adapter()
    doc_source_assignments = {
        job.doc_id: (job.publish_status.diagnostics or {}).get("knowledge_source_name", settings.azure_search_knowledge_source_name)
        for job in jobs
    }
    if isinstance(adapter, LocalPreviewAdapter):
        chunks = []
        from backend.domain.models import ChunkRecord

        for job in jobs:
            payload = json.loads(Path(job.chunks_path).read_text(encoding="utf-8"))
            chunks.extend(ChunkRecord.model_validate(item) for item in payload)
        response = local_preview_chat(request.question, chunks, doc_ids=selected_doc_ids or None)
        response.diagnostics["corpus_mode"] = request.corpus_mode
        response.diagnostics["selected_doc_ids"] = selected_doc_ids
        response.diagnostics["selected_corpora"] = [
            {"doc_id": job.doc_id, "file_name": job.file_name}
            for job in jobs
            if not selected_doc_ids or job.doc_id in selected_doc_ids
        ]
        return response

    try:
        payload = adapter.chat(
            request.question,
            doc_ids=selected_doc_ids or None,
            doc_source_assignments=doc_source_assignments,
        )
        response = synthesize_grounded_chat(request.question, payload)
        response.diagnostics["corpus_mode"] = request.corpus_mode
        response.diagnostics["selected_doc_ids"] = selected_doc_ids
        response.diagnostics["selected_corpora"] = [
            {"doc_id": job.doc_id, "file_name": job.file_name}
            for job in jobs
            if not selected_doc_ids or job.doc_id in selected_doc_ids
        ]
        return response
    except Exception as exc:  # pragma: no cover - API safety
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/")
def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")
