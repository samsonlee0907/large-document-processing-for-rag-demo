from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.domain.models import ChatCitation, ChatTurnResponse, ChunkRecord
from backend.services.foundry_openai import call_foundry_text
from backend.services.job_store import job_store


def _extract_answer_text(payload: dict[str, Any]) -> str:
    answer = payload.get("answer")
    if isinstance(answer, str):
        return answer

    response_items = payload.get("response")
    if isinstance(response_items, list):
        texts: list[str] = []
        for item in response_items:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict):
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
        if texts:
            return "\n\n".join(texts)

    if isinstance(response_items, str):
        return response_items

    return "No answer returned."


def _parse_image_evidence(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        return [item for item in raw_value if isinstance(item, dict)]
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _normalize_citation(item: dict[str, Any]) -> ChatCitation | None:
    title = item.get("title") or item.get("source_name") or item.get("knowledgeSourceName") or "Source"
    uri = item.get("url") or item.get("uri") or item.get("sourceUri") or item.get("source_uri")
    chunk_id = item.get("chunk_id") or item.get("chunkId") or item.get("id")
    doc_id = item.get("doc_id")
    page_numbers = item.get("page_numbers") or []
    if not isinstance(page_numbers, list):
        page_numbers = []
    image_evidence = _parse_image_evidence(item.get("image_evidence_json"))
    snippet = (
        item.get("snippet")
        or item.get("content")
        or item.get("text")
        or item.get("clean_text")
        or item.get("answer")
        or ""
    )
    if not isinstance(snippet, str):
        snippet = json.dumps(snippet, ensure_ascii=True)
    snippet = " ".join(snippet.split())[:360]
    return ChatCitation(
        title=title,
        uri=uri,
        chunk_id=chunk_id,
        doc_id=doc_id,
        page_numbers=page_numbers,
        snippet=snippet,
        image_evidence=image_evidence,
    )


def _extract_text_embedded_references(payload: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    response_items = payload.get("response")
    if not isinstance(response_items, list):
        return references
    for item in response_items:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                references.extend(entry for entry in parsed if isinstance(entry, dict))
            elif isinstance(parsed, dict):
                references.append(parsed)
    return references


def _extract_citations(payload: dict[str, Any]) -> list[ChatCitation]:
    citations: list[ChatCitation] = []

    for item in payload.get("results") or payload.get("citations") or []:
        if not isinstance(item, dict):
            continue
        citation = _normalize_citation(item)
        if citation:
            citations.append(citation)

    if citations:
        return citations[:8]

    for item in payload.get("activity", []):
        if not isinstance(item, dict):
            continue
        for reference in item.get("references", []):
            if not isinstance(reference, dict):
                continue
            citation = _normalize_citation(reference)
            if citation:
                citations.append(citation)
        if len(citations) >= 8:
            break

    if citations:
        return citations[:8]

    for item in _extract_text_embedded_references(payload):
        citation = _normalize_citation(item)
        if citation:
            citations.append(citation)
        if len(citations) >= 8:
            break
    return _hydrate_citations(citations[:8])


def _infer_page_numbers(snippet: str) -> list[int]:
    matches = re.findall(r"\b[Pp]age\s+(\d+)\b", snippet)
    return [int(match) for match in matches[:4]]


def _hydrate_citations(citations: list[ChatCitation]) -> list[ChatCitation]:
    jobs = [job for job in job_store.list_jobs() if job.intermediate_path and Path(job.intermediate_path).exists()]
    for citation in citations:
        if citation.doc_id and citation.image_evidence and citation.page_numbers:
            continue
        matched_job = next(
            (
                job
                for job in jobs
                if citation.doc_id == job.doc_id
                or citation.title == job.file_name
                or citation.title == Path(job.stored_path).name
            ),
            None,
        )
        if not matched_job:
            continue
        citation.doc_id = citation.doc_id or matched_job.doc_id
        if not citation.page_numbers:
            citation.page_numbers = _infer_page_numbers(citation.snippet)
        intermediate = json.loads(Path(matched_job.intermediate_path).read_text(encoding="utf-8"))
        figures = (intermediate.get("metadata") or {}).get("figure_artifacts") or []
        if citation.image_evidence:
            continue
        if citation.page_numbers:
            citation.image_evidence = [
                figure
                for figure in figures
                if isinstance(figure, dict) and figure.get("page_number") in citation.page_numbers
            ][:2]
    return citations


def _extract_subqueries(activity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    subqueries: list[dict[str, Any]] = []
    for index, item in enumerate(activity, start=1):
        if not isinstance(item, dict) or item.get("type") != "searchIndex":
            continue
        args = item.get("searchIndexArguments") or {}
        subqueries.append(
            {
                "step": len(subqueries) + 1,
                "search": args.get("search") or "",
                "knowledge_source": item.get("knowledgeSourceName"),
                "result_count": item.get("count"),
                "elapsed_ms": item.get("elapsedMs"),
                "raw_activity_id": item.get("id", index),
            }
        )
    return subqueries


def build_chat_response(payload: dict[str, Any]) -> ChatTurnResponse:
    citations = _extract_citations(payload)
    answer = _extract_answer_text(payload)
    diagnostics = payload.get("diagnostics") or {}
    if "activity" in payload:
        diagnostics["activity"] = payload["activity"]
        diagnostics["subqueries"] = _extract_subqueries(payload["activity"])
    diagnostics.setdefault("mode", "search_raw")
    return ChatTurnResponse(answer=answer, citations=citations, diagnostics=diagnostics)


def _format_sources_for_prompt(citations: list[ChatCitation]) -> str:
    blocks: list[str] = []
    for index, citation in enumerate(citations, start=1):
        source_lines = [f"[{index}] {citation.title}"]
        if citation.chunk_id:
            source_lines.append(f"chunk_id: {citation.chunk_id}")
        if citation.doc_id:
            source_lines.append(f"doc_id: {citation.doc_id}")
        if citation.page_numbers:
            source_lines.append(f"pages: {', '.join(str(page) for page in citation.page_numbers)}")
        if citation.uri:
            source_lines.append(f"uri: {citation.uri}")
        source_lines.append(f"content: {citation.snippet or 'No snippet available.'}")
        for image in citation.image_evidence[:2]:
            description = image.get("description")
            if description:
                source_lines.append(f"image: {description}")
        blocks.append("\n".join(source_lines))
    return "\n\n".join(blocks)


def synthesize_grounded_chat(question: str, retrieval_payload: dict[str, Any]) -> ChatTurnResponse:
    citations = _extract_citations(retrieval_payload)
    if not citations:
        return build_chat_response(retrieval_payload)

    if not settings.azure_foundry_chat_enabled:
        response = build_chat_response(retrieval_payload)
        response.diagnostics["mode"] = "search_raw"
        return response

    prompt_sources = _format_sources_for_prompt(citations)
    system_message = (
        "You answer enterprise knowledge questions using only the grounded sources provided. "
        "Do not invent facts. If the evidence is insufficient, say so clearly. "
        "Cite claims inline using square brackets like [1] or [2][3]. "
        "If figure descriptions are provided, use them only as supporting evidence."
    )
    user_message = (
        f"Question:\n{question}\n\n"
        f"Grounded sources:\n{prompt_sources}\n\n"
        "Write a direct answer grounded only in these sources."
    )
    answer, endpoint = call_foundry_text(
        [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]
    )
    diagnostics = retrieval_payload.get("diagnostics") or {}
    if "activity" in retrieval_payload:
        diagnostics["activity"] = retrieval_payload["activity"]
        diagnostics["subqueries"] = _extract_subqueries(retrieval_payload["activity"])
    diagnostics.update(
        {
            "mode": "search_plus_gpt54",
            "model": settings.azure_foundry_chat_deployment,
            "model_endpoint": endpoint,
            "grounding_source_count": len(citations),
        }
    )
    return ChatTurnResponse(answer=answer, citations=citations, diagnostics=diagnostics)


def local_preview_chat(question: str, chunks: list[ChunkRecord], *, doc_ids: list[str] | None = None) -> ChatTurnResponse:
    if doc_ids:
        allowed = set(doc_ids)
        chunks = [chunk for chunk in chunks if chunk.doc_id in allowed]
    scored = []
    query_terms = {term.lower() for term in question.split() if len(term) > 2}
    for chunk in chunks:
        text = chunk.clean_text.lower()
        score = sum(1 for term in query_terms if term in text)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    top_chunks = [item[1] for item in scored[:3]]
    if not top_chunks:
        return ChatTurnResponse(
            answer="No relevant chunk was found in local preview mode. Configure Azure Search for true agentic retrieval.",
            diagnostics={"mode": "local_preview", "subqueries": [], "selected_doc_ids": doc_ids or []},
        )
    answer = "\n\n".join(chunk.clean_text[:360] for chunk in top_chunks)
    citations = [
        ChatCitation(
            title=chunk.source_name,
            uri=chunk.source_uri,
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            page_numbers=chunk.page_numbers,
            snippet=chunk.clean_text[:200],
            image_evidence=chunk.image_evidence[:2],
        )
        for chunk in top_chunks
    ]
    return ChatTurnResponse(
        answer=answer,
        citations=citations,
        diagnostics={"mode": "local_preview", "subqueries": [], "selected_doc_ids": doc_ids or []},
    )
