from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

from backend.core.config import settings
from backend.domain.models import ChatCitation, ChatTurnResponse, ChunkRecord
from backend.services.foundry_openai import call_foundry_text
from backend.services.job_store import job_store

MAX_CHAT_CITATIONS = 8


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


def _normalize_citation(
    item: dict[str, Any],
    *,
    evidence_kind: str = "retrieval_reference",
    knowledge_source: str | None = None,
    index_name: str | None = None,
    supporting_query: str | None = None,
    retrieval_step: int | None = None,
) -> ChatCitation | None:
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
        knowledge_source=knowledge_source or item.get("knowledgeSourceName") or item.get("knowledge_source"),
        index_name=index_name or item.get("index_name"),
        evidence_kind=evidence_kind,
        supporting_query=supporting_query,
        retrieval_step=retrieval_step,
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


def _collect_raw_citation_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for item in payload.get("results") or payload.get("citations") or []:
        if isinstance(item, dict):
            items.append(item)

    for item in payload.get("activity", []):
        if not isinstance(item, dict):
            continue
        for reference in item.get("references", []):
            if not isinstance(reference, dict):
                continue
            items.append(
                {
                    **reference,
                    "knowledgeSourceName": reference.get("knowledgeSourceName") or item.get("knowledgeSourceName"),
                }
            )

    for item in _extract_text_embedded_references(payload):
        if isinstance(item, dict):
            items.append(item)

    return items


def _infer_page_numbers(snippet: str) -> list[int]:
    matches = re.findall(r"\b[Pp]age\s+(\d+)\b", snippet)
    return [int(match) for match in matches[:4]]


def _job_lookup() -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    jobs = [job for job in job_store.list_jobs() if job.intermediate_path and Path(job.intermediate_path).exists()]
    jobs_by_doc_id = {job.doc_id: job for job in jobs}
    jobs_by_title = {}
    for job in jobs:
        jobs_by_title[job.file_name] = job
        jobs_by_title[Path(job.stored_path).name] = job
    return jobs, jobs_by_doc_id, jobs_by_title


def _citation_richness(citation: ChatCitation) -> int:
    score = 0
    if citation.knowledge_source:
        score += 5
    if citation.index_name:
        score += 3
    if citation.doc_id:
        score += 4
    if citation.chunk_id:
        score += 3
    if citation.page_numbers:
        score += 1
    if citation.uri:
        score += 1
    if citation.image_evidence:
        score += 1
    if citation.evidence_kind == "activity_support":
        score += 1
    return score


def _snippet_fingerprint(snippet: str) -> str:
    return re.sub(r"\s+", " ", snippet.strip().lower())[:220]


def _hydrate_citations(citations: list[ChatCitation]) -> list[ChatCitation]:
    jobs, jobs_by_doc_id, jobs_by_title = _job_lookup()
    for citation in citations:
        if citation.doc_id and citation.image_evidence and citation.page_numbers:
            continue
        matched_job = jobs_by_doc_id.get(citation.doc_id) if citation.doc_id else None
        if not matched_job:
            matched_job = jobs_by_title.get(citation.title)
        if not matched_job:
            continue
        citation.doc_id = citation.doc_id or matched_job.doc_id
        publish_diagnostics = matched_job.publish_status.diagnostics or {}
        citation.knowledge_source = citation.knowledge_source or publish_diagnostics.get("knowledge_source_name")
        citation.index_name = citation.index_name or publish_diagnostics.get("index_name")
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


def _dedupe_citations(citations: list[ChatCitation]) -> list[ChatCitation]:
    ranked = sorted(
        enumerate(citations),
        key=lambda item: (-_citation_richness(item[1]), item[0]),
    )
    deduped: list[ChatCitation] = []
    seen_primary: set[tuple[str, str]] = set()
    seen_snippets: set[str] = set()
    for _, citation in ranked:
        primary = citation.chunk_id or citation.doc_id or citation.title
        secondary = citation.snippet[:160]
        primary_key = (str(primary), secondary)
        snippet_key = _snippet_fingerprint(citation.snippet)
        if primary_key in seen_primary:
            continue
        if snippet_key and snippet_key in seen_snippets:
            continue
        seen_primary.add(primary_key)
        if snippet_key:
            seen_snippets.add(snippet_key)
        deduped.append(citation)
    return deduped


def _source_key(citation: ChatCitation) -> str:
    return (
        citation.knowledge_source
        or citation.index_name
        or citation.doc_id
        or citation.title
    )


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


def _effective_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    diagnostics = dict(payload.get("diagnostics") or {})
    activity = payload.get("activity")
    if isinstance(activity, list):
        diagnostics["activity"] = activity
        diagnostics.setdefault("subqueries", _extract_subqueries(activity))
    return diagnostics


def _extract_source_maps(diagnostics: dict[str, Any]) -> dict[str, str]:
    if isinstance(diagnostics.get("knowledge_source_index_map"), dict):
        return {
            str(key): str(value)
            for key, value in diagnostics["knowledge_source_index_map"].items()
            if key and value
        }
    knowledge_sources = diagnostics.get("available_knowledge_sources") or diagnostics.get("selected_knowledge_sources") or []
    indexes = diagnostics.get("available_search_indexes") or diagnostics.get("selected_search_indexes") or []
    mapping: dict[str, str] = {}
    for source_name, index_name in zip(knowledge_sources, indexes):
        if source_name and index_name:
            mapping[str(source_name)] = str(index_name)
    return mapping


def _positive_sources_from_diagnostics(diagnostics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for subquery in diagnostics.get("subqueries") or []:
        if not isinstance(subquery, dict):
            continue
        source_name = subquery.get("knowledge_source")
        result_count = int(subquery.get("result_count") or 0)
        if not source_name or result_count <= 0:
            continue
        best = by_source.get(source_name)
        if not best or result_count > int(best.get("result_count") or 0):
            by_source[source_name] = subquery
    return by_source


def _build_doc_filter(doc_ids: list[str]) -> str:
    unique_ids: list[str] = []
    seen = set()
    for doc_id in doc_ids:
        normalized = str(doc_id).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_ids.append(normalized)
    clauses = []
    for value in unique_ids:
        escaped = value.replace("'", "''")
        clauses.append(f"doc_id eq '{escaped}'")
    return " or ".join(clauses)


def _search_supporting_chunks(
    *,
    index_name: str,
    query: str,
    knowledge_source: str,
    retrieval_step: int | None,
    doc_ids: list[str] | None = None,
    top: int = 2,
) -> list[ChatCitation]:
    endpoint = settings.azure_search_endpoint.rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "api-key": settings.azure_search_key,
    }
    url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2025-09-01"
    select_fields = ",".join(
        [
            "chunk_id",
            "doc_id",
            "source_name",
            "source_uri",
            "section_path",
            "page_numbers",
            "clean_text",
            "image_evidence_json",
        ]
    )
    filter_expression = _build_doc_filter(doc_ids or [])
    request_variants = [
        {
            "search": query,
            "top": top,
            "queryType": "semantic",
            "semanticConfiguration": "default-semantic-config",
            "select": select_fields,
            **({"filter": filter_expression} if filter_expression else {}),
        },
        {
            "search": query,
            "top": top,
            "select": select_fields,
            **({"filter": filter_expression} if filter_expression else {}),
        },
    ]

    last_error: Exception | None = None
    for body in request_variants:
        try:
            response = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
            response.raise_for_status()
            payload = response.json()
            citations: list[ChatCitation] = []
            for item in payload.get("value") or []:
                if not isinstance(item, dict):
                    continue
                snippet = item.get("clean_text") or ""
                captions = item.get("@search.captions") or []
                if isinstance(captions, list) and captions:
                    first_caption = captions[0]
                    if isinstance(first_caption, dict) and isinstance(first_caption.get("text"), str):
                        snippet = first_caption["text"]
                citation = _normalize_citation(
                    {
                        **item,
                        "snippet": snippet,
                    },
                    evidence_kind="activity_support",
                    knowledge_source=knowledge_source,
                    index_name=index_name,
                    supporting_query=query,
                    retrieval_step=retrieval_step,
                )
                if citation:
                    citations.append(citation)
            return citations
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        return []
    return []


def _supplement_missing_sources(
    citations: list[ChatCitation],
    diagnostics: dict[str, Any],
) -> list[ChatCitation]:
    source_map = _extract_source_maps(diagnostics)
    positive_sources = _positive_sources_from_diagnostics(diagnostics)
    represented_sources = {_source_key(citation) for citation in citations if _source_key(citation)}
    custom_scope_groups = diagnostics.get("custom_scope_groups") or {}

    supplemental: list[ChatCitation] = []
    for source_name, subquery in positive_sources.items():
        if source_name in represented_sources:
            continue
        index_name = source_map.get(source_name)
        if not index_name:
            continue
        query = str(subquery.get("search") or "").strip()
        if not query:
            continue
        doc_ids = custom_scope_groups.get(source_name) if isinstance(custom_scope_groups, dict) else None
        supplemental.extend(
            _search_supporting_chunks(
                index_name=index_name,
                query=query,
                knowledge_source=source_name,
                retrieval_step=subquery.get("step"),
                doc_ids=doc_ids,
                top=2,
            )
        )
    return supplemental


def _balance_citations(citations: list[ChatCitation], diagnostics: dict[str, Any]) -> list[ChatCitation]:
    positive_sources = list(_positive_sources_from_diagnostics(diagnostics).keys())
    ordered: list[ChatCitation] = []
    used: set[int] = set()

    for source_name in positive_sources:
        for index, citation in enumerate(citations):
            if index in used:
                continue
            if citation.knowledge_source == source_name:
                ordered.append(citation)
                used.add(index)
                break

    for index, citation in enumerate(citations):
        if index in used:
            continue
        ordered.append(citation)
        used.add(index)

    return ordered[:MAX_CHAT_CITATIONS]


def _assign_reference_ids(citations: list[ChatCitation]) -> list[ChatCitation]:
    for index, citation in enumerate(citations, start=1):
        citation.reference_id = index
    return citations


def _summarize_evidence(citations: list[ChatCitation], diagnostics: dict[str, Any]) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    for citation in citations:
        source_name = citation.knowledge_source or "unknown"
        source_counts[source_name] = source_counts.get(source_name, 0) + 1
    positive_sources = _positive_sources_from_diagnostics(diagnostics)
    return {
        "positive_retrieval_sources": sorted(positive_sources.keys()),
        "evidence_source_counts": source_counts,
        "represented_knowledge_sources": sorted(source_counts.keys()),
        "missing_positive_sources": sorted(set(positive_sources.keys()) - set(source_counts.keys())),
    }


def _extract_citations(payload: dict[str, Any]) -> list[ChatCitation]:
    diagnostics = _effective_diagnostics(payload)
    citations: list[ChatCitation] = []
    for item in _collect_raw_citation_items(payload):
        citation = _normalize_citation(item)
        if citation:
            citations.append(citation)

    citations = _hydrate_citations(citations)
    citations = _dedupe_citations(citations)

    supplemental = _supplement_missing_sources(citations, diagnostics)
    if supplemental:
        citations.extend(_hydrate_citations(supplemental))
        citations = _dedupe_citations(citations)

    citations = _balance_citations(citations, diagnostics)
    return _assign_reference_ids(citations)


def build_chat_response(payload: dict[str, Any]) -> ChatTurnResponse:
    citations = _extract_citations(payload)
    answer = _extract_answer_text(payload)
    diagnostics = _effective_diagnostics(payload)
    diagnostics.update(_summarize_evidence(citations, diagnostics))
    diagnostics.setdefault("mode", "search_raw")
    return ChatTurnResponse(answer=answer, citations=citations, diagnostics=diagnostics)


def _format_sources_for_prompt(citations: list[ChatCitation]) -> str:
    blocks: list[str] = []
    for citation in citations:
        reference_id = citation.reference_id or len(blocks) + 1
        source_lines = [f"[{reference_id}] {citation.title}"]
        if citation.chunk_id:
            source_lines.append(f"chunk_id: {citation.chunk_id}")
        if citation.doc_id:
            source_lines.append(f"doc_id: {citation.doc_id}")
        if citation.knowledge_source:
            source_lines.append(f"knowledge_source: {citation.knowledge_source}")
        if citation.index_name:
            source_lines.append(f"index_name: {citation.index_name}")
        if citation.page_numbers:
            source_lines.append(f"pages: {', '.join(str(page) for page in citation.page_numbers)}")
        if citation.uri:
            source_lines.append(f"uri: {citation.uri}")
        if citation.supporting_query:
            source_lines.append(f"supporting_query: {citation.supporting_query}")
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
    diagnostics = _effective_diagnostics(retrieval_payload)
    diagnostics.update(_summarize_evidence(citations, diagnostics))
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
    citations = _assign_reference_ids(citations)
    return ChatTurnResponse(
        answer=answer,
        citations=citations,
        diagnostics={
            "mode": "local_preview",
            "subqueries": [],
            "selected_doc_ids": doc_ids or [],
            **_summarize_evidence(citations, {"subqueries": []}),
        },
    )
