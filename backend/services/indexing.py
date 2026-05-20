from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import requests

from backend.core.config import SearchKnowledgeSourceConfig, settings
from backend.domain.models import ChunkRecord, PublishStatus

logger = logging.getLogger(__name__)

ROUTING_STOPWORDS = {
    "about",
    "after",
    "against",
    "answer",
    "asked",
    "corpus",
    "data",
    "document",
    "documents",
    "explain",
    "from",
    "index",
    "indexes",
    "into",
    "knowledge",
    "query",
    "report",
    "reports",
    "search",
    "show",
    "source",
    "sources",
    "tell",
    "that",
    "their",
    "them",
    "these",
    "those",
    "what",
    "which",
    "with",
    "would",
}


class FoundryIQAdapter:
    def publish(
        self,
        chunks: list[ChunkRecord],
        *,
        source_name: str | None = None,
        route_text: str | None = None,
    ) -> PublishStatus:
        raise NotImplementedError

    def get_status(self) -> PublishStatus:
        raise NotImplementedError

    def chat(
        self,
        question: str,
        *,
        doc_ids: list[str] | None = None,
        doc_source_assignments: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def delete_chunks(self, chunks: list[ChunkRecord], *, index_name: str | None = None) -> None:
        raise NotImplementedError


class LocalPreviewAdapter(FoundryIQAdapter):
    def publish(
        self,
        chunks: list[ChunkRecord],
        *,
        source_name: str | None = None,
        route_text: str | None = None,
    ) -> PublishStatus:
        return PublishStatus(
            mode="local_preview",
            resource="Azure AI Search Knowledge Base",
            ready=True,
            last_sync_time=datetime.now(timezone.utc).isoformat(),
            indexed_document_count=len({chunk.doc_id for chunk in chunks}),
            indexed_chunk_count=len(chunks),
            message="Azure Search is not configured. Using local retrieval preview for chat.",
        )

    def get_status(self) -> PublishStatus:
        return PublishStatus(
            mode="local_preview",
            resource="Azure AI Search Knowledge Base",
            ready=False,
            message="Azure Search is not configured. Configure it to publish a real knowledge base.",
        )

    def chat(
        self,
        question: str,
        *,
        doc_ids: list[str] | None = None,
        doc_source_assignments: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": "Azure Search is not configured. Local preview mode can only answer over ingested chunks stored in the app.",
            "citations": [],
            "diagnostics": {"mode": "local_preview", "question": question, "selected_doc_ids": doc_ids or []},
        }

    def delete_chunks(self, chunks: list[ChunkRecord], *, index_name: str | None = None) -> None:
        return


class AzureSearchKnowledgeBaseAdapter(FoundryIQAdapter):
    def __init__(self) -> None:
        self.endpoint = settings.azure_search_endpoint.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "api-key": settings.azure_search_key,
            "Prefer": "return=representation",
        }
        self.api_version = settings.azure_search_api_version

    @property
    def _is_preview_api(self) -> bool:
        return "preview" in self.api_version

    def publish(
        self,
        chunks: list[ChunkRecord],
        *,
        source_name: str | None = None,
        route_text: str | None = None,
    ) -> PublishStatus:
        target_source, assignment_diagnostics = self._select_target_source_for_document(
            source_name=source_name,
            route_text=route_text,
        )
        self._ensure_indexes()
        self._upload_chunks(chunks, target_source.index_name)
        if self.api_version in {"2026-04-01", "2025-11-01-preview"}:
            self._ensure_knowledge_sources()
            self._ensure_knowledge_base()
        configured_sources = self._configured_knowledge_sources()
        return PublishStatus(
            mode="search_knowledge_base",
            resource=settings.azure_search_knowledge_base_name,
            ready=True,
            last_sync_time=datetime.now(timezone.utc).isoformat(),
            indexed_document_count=len({chunk.doc_id for chunk in chunks}),
            indexed_chunk_count=len(chunks),
            message="Chunks published to Azure AI Search and associated knowledge base resources ensured.",
            diagnostics={
                "index_name": target_source.index_name,
                "knowledge_source_name": target_source.knowledge_source_name,
                "knowledge_base_name": settings.azure_search_knowledge_base_name,
                "index_names": [source.index_name for source in configured_sources],
                "knowledge_source_names": [source.knowledge_source_name for source in configured_sources],
                "multi_index_enabled": len(configured_sources) > 1,
                **assignment_diagnostics,
            },
        )

    def get_status(self) -> PublishStatus:
        if not settings.azure_search_enabled:
            return LocalPreviewAdapter().get_status()
        configured_sources = self._configured_knowledge_sources()
        return PublishStatus(
            mode="search_knowledge_base",
            resource=settings.azure_search_knowledge_base_name,
            ready=True,
            message="Azure Search knowledge base publishing is configured.",
            diagnostics={
                "index_name": settings.azure_search_index_name,
                "knowledge_source_name": settings.azure_search_knowledge_source_name,
                "knowledge_base_name": settings.azure_search_knowledge_base_name,
                "index_names": [source.index_name for source in configured_sources],
                "knowledge_source_names": [source.knowledge_source_name for source in configured_sources],
                "multi_index_enabled": len(configured_sources) > 1,
            },
        )

    def chat(
        self,
        question: str,
        *,
        doc_ids: list[str] | None = None,
        doc_source_assignments: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        selected_sources, routing_diagnostics = self._route_knowledge_sources(
            question,
            doc_ids=doc_ids,
            doc_source_assignments=doc_source_assignments,
        )
        grouped_doc_ids = self._group_doc_ids_by_source(doc_ids or [], doc_source_assignments or {})
        knowledge_source_params = [
            self._build_knowledge_source_params(
                source,
                doc_ids=grouped_doc_ids.get(source.knowledge_source_name),
                force_query=len(selected_sources) > 1 or bool(doc_ids),
            )
            for source in selected_sources
        ]
        payload = self._build_retrieve_payload(question, knowledge_source_params)
        url = (
            f"{self.endpoint}/knowledgebases('{settings.azure_search_knowledge_base_name}')/retrieve"
            f"?api-version={self.api_version}"
        )
        response = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=60)
        self._raise_for_status(response)
        result = response.json()
        diagnostics = result.setdefault("diagnostics", {})
        diagnostics["selected_doc_ids"] = doc_ids or []
        diagnostics["corpus_mode"] = "custom" if doc_ids else "auto"
        diagnostics.update(routing_diagnostics)
        return result

    def delete_chunks(self, chunks: list[ChunkRecord], *, index_name: str | None = None) -> None:
        if not chunks:
            return
        target_index = index_name or settings.azure_search_index_name
        url = f"{self.endpoint}/indexes/{target_index}/docs/index?api-version=2025-09-01"
        actions = [{"@search.action": "delete", "chunk_id": chunk.chunk_id} for chunk in chunks]
        response = requests.post(url, headers=self.headers, data=json.dumps({"value": actions}), timeout=60)
        self._raise_for_status(response)

    def _ensure_indexes(self) -> None:
        for source in self._configured_knowledge_sources():
            self._ensure_index(source.index_name)

    def _ensure_index(self, index_name: str) -> None:
        url = f"{self.endpoint}/indexes/{index_name}?api-version=2025-09-01"
        body = {
            "name": index_name,
            "fields": [
                {"name": "chunk_id", "type": "Edm.String", "key": True, "searchable": False, "filterable": True},
                {"name": "doc_id", "type": "Edm.String", "searchable": False, "filterable": True},
                {"name": "source_name", "type": "Edm.String", "searchable": True, "filterable": True, "retrievable": True},
                {"name": "source_uri", "type": "Edm.String", "searchable": False, "retrievable": True},
                {"name": "section_path", "type": "Collection(Edm.String)", "searchable": True, "retrievable": True},
                {"name": "page_numbers", "type": "Collection(Edm.Int32)", "filterable": True, "retrievable": True},
                {"name": "content_type", "type": "Edm.String", "filterable": True, "retrievable": True},
                {"name": "tags", "type": "Collection(Edm.String)", "filterable": True, "retrievable": True},
                {"name": "checksum", "type": "Edm.String", "filterable": True, "retrievable": True},
                {"name": "last_updated", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True, "retrievable": True},
                {"name": "clean_text", "type": "Edm.String", "searchable": True, "retrievable": True},
                {"name": "image_evidence_json", "type": "Edm.String", "searchable": False, "retrievable": True},
            ],
            "semantic": {
                "defaultConfiguration": "default-semantic-config",
                "configurations": [
                    {
                        "name": "default-semantic-config",
                        "prioritizedFields": {
                            "titleField": {"fieldName": "source_name"},
                            "prioritizedContentFields": [{"fieldName": "clean_text"}],
                            "prioritizedKeywordsFields": [{"fieldName": "tags"}],
                        },
                    }
                ],
            },
        }
        response = requests.put(url, headers=self.headers, data=json.dumps(body), timeout=60)
        self._raise_for_status(response)

    def _upload_chunks(self, chunks: list[ChunkRecord], index_name: str | None = None) -> None:
        target_index = index_name or settings.azure_search_index_name
        url = f"{self.endpoint}/indexes/{target_index}/docs/index?api-version=2025-09-01"
        actions = []
        for chunk in chunks:
            actions.append(
                {
                    "@search.action": "mergeOrUpload",
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "source_name": chunk.source_name,
                    "source_uri": chunk.source_uri,
                    "section_path": chunk.section_path,
                    "page_numbers": chunk.page_numbers,
                    "content_type": chunk.content_type,
                    "tags": chunk.tags,
                    "checksum": chunk.checksum,
                    "last_updated": chunk.last_updated,
                    "clean_text": chunk.clean_text,
                    "image_evidence_json": json.dumps(chunk.image_evidence),
                }
            )
        response = requests.post(url, headers=self.headers, data=json.dumps({"value": actions}), timeout=60)
        self._raise_for_status(response)

    def _ensure_knowledge_sources(self) -> None:
        for source in self._configured_knowledge_sources():
            self._ensure_knowledge_source(source)

    def _ensure_knowledge_source(self, source: SearchKnowledgeSourceConfig) -> None:
        url = (
            f"{self.endpoint}/knowledgesources('{source.knowledge_source_name}')"
            f"?api-version={self.api_version}"
        )
        body = {
            "name": source.knowledge_source_name,
            "kind": "searchIndex",
            "searchIndexParameters": {
                "searchIndexName": source.index_name,
                "semanticConfigurationName": source.semantic_configuration_name,
                "sourceDataFields": [
                    {"name": field_name}
                    for field_name in source.source_data_fields
                ],
                "searchFields": [
                    {"name": field_name}
                    for field_name in source.search_fields
                ],
            },
        }
        response = requests.put(url, headers=self.headers, data=json.dumps(body), timeout=60)
        self._raise_for_status(response)

    def _ensure_knowledge_base(self) -> None:
        url = (
            f"{self.endpoint}/knowledgebases('{settings.azure_search_knowledge_base_name}')"
            f"?api-version={self.api_version}"
        )
        body = self._knowledge_base_body()
        response = requests.put(url, headers=self.headers, data=json.dumps(body), timeout=60)
        self._raise_for_status(response)

        if self._is_preview_api and settings.azure_search_llm_enabled:
            current = self._get_knowledge_base(settings.azure_search_knowledge_base_name)
            models = current.get("models") if isinstance(current, dict) else None
            if not models:
                self._delete_knowledge_base(settings.azure_search_knowledge_base_name)
                recreate = requests.put(url, headers=self.headers, data=json.dumps(body), timeout=60)
                self._raise_for_status(recreate)

    def _knowledge_base_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": settings.azure_search_knowledge_base_name,
            "knowledgeSources": [
                {"name": source.knowledge_source_name}
                for source in self._configured_knowledge_sources()
            ],
        }
        if self._is_preview_api and settings.azure_search_llm_enabled:
            azure_openai_parameters: dict[str, Any] = {
                "resourceUri": settings.azure_foundry_openai_base_url,
                "deploymentId": settings.azure_search_llm_deployment,
                "modelName": settings.azure_search_llm_model_name or settings.azure_search_llm_deployment,
            }
            if not settings.azure_search_llm_use_managed_identity:
                azure_openai_parameters["apiKey"] = settings.azure_foundry_api_key
            body["models"] = [
                {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": azure_openai_parameters,
                }
            ]
            body["retrievalReasoningEffort"] = {"kind": settings.azure_search_llm_reasoning_effort}
            body["outputMode"] = "extractiveData"
        return body

    def _get_knowledge_base(self, knowledge_base_name: str) -> dict[str, Any]:
        url = f"{self.endpoint}/knowledgebases('{knowledge_base_name}')?api-version={self.api_version}"
        response = requests.get(url, headers=self.headers, timeout=60)
        if response.status_code == 404:
            return {}
        self._raise_for_status(response)
        return response.json()

    def _delete_knowledge_base(self, knowledge_base_name: str) -> None:
        url = f"{self.endpoint}/knowledgebases('{knowledge_base_name}')?api-version={self.api_version}"
        response = requests.delete(url, headers=self.headers, timeout=60)
        if response.status_code not in {200, 204, 404}:
            self._raise_for_status(response)

    def _build_doc_filter(self, doc_ids: list[str]) -> str:
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

    def _primary_knowledge_source(self) -> SearchKnowledgeSourceConfig:
        return SearchKnowledgeSourceConfig(
            knowledge_source_name=settings.azure_search_knowledge_source_name,
            index_name=settings.azure_search_index_name,
            description="Primary application corpus index for uploaded and generated documents.",
        )

    def _configured_knowledge_sources(self) -> list[SearchKnowledgeSourceConfig]:
        sources: list[SearchKnowledgeSourceConfig] = []
        seen_names: set[str] = set()
        for source in (self._primary_knowledge_source(), *settings.azure_search_extra_sources):
            if source.knowledge_source_name in seen_names:
                continue
            seen_names.add(source.knowledge_source_name)
            sources.append(source)
        return sources

    def _build_knowledge_source_params(
        self,
        source: SearchKnowledgeSourceConfig,
        *,
        doc_ids: list[str] | None,
        force_query: bool,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "knowledgeSourceName": source.knowledge_source_name,
            "kind": "searchIndex",
            "includeReferences": True,
            "includeReferenceSourceData": True,
        }
        if doc_ids:
            params["filterAddOn"] = self._build_doc_filter(doc_ids)
        if self._is_preview_api and force_query:
            params["alwaysQuerySource"] = True
        return params

    def _route_knowledge_sources(
        self,
        question: str,
        *,
        doc_ids: list[str] | None = None,
        doc_source_assignments: dict[str, str] | None = None,
    ) -> tuple[list[SearchKnowledgeSourceConfig], dict[str, Any]]:
        configured_sources = self._configured_knowledge_sources()
        source_by_name = {source.knowledge_source_name: source for source in configured_sources}
        diagnostics: dict[str, Any] = {
            "available_knowledge_sources": [source.knowledge_source_name for source in configured_sources],
            "available_search_indexes": [source.index_name for source in configured_sources],
            "knowledge_source_index_map": {
                source.knowledge_source_name: source.index_name
                for source in configured_sources
            },
            "knowledge_source_match_details": [],
        }
        if doc_ids:
            grouped_doc_ids = self._group_doc_ids_by_source(doc_ids, doc_source_assignments or {})
            selected = [
                source_by_name[source_name]
                for source_name in grouped_doc_ids
                if source_name in source_by_name
            ]
            if not selected:
                selected = [self._primary_knowledge_source()]
            diagnostics.update(
                {
                    "routing_mode": "custom_doc_scope",
                    "routing_reason": "Custom corpus selection is grouped by the assigned knowledge source for each selected document.",
                    "selected_knowledge_sources": [source.knowledge_source_name for source in selected],
                    "selected_search_indexes": [source.index_name for source in selected],
                    "multi_index_routing": len(selected) > 1,
                    "custom_scope_groups": grouped_doc_ids,
                }
            )
            return selected, diagnostics
        if len(configured_sources) == 1:
            primary = configured_sources[0]
            diagnostics.update(
                {
                    "routing_mode": "single_index",
                    "routing_reason": "No extra Azure AI Search knowledge sources are configured.",
                    "selected_knowledge_sources": [primary.knowledge_source_name],
                    "selected_search_indexes": [primary.index_name],
                    "multi_index_routing": False,
                }
            )
            return [primary], diagnostics

        question_lower = question.lower()
        tokens = self._tokenize_routing_text(question_lower)
        cross_source_intent = self._has_cross_source_intent(question_lower, tokens)
        matched_sources: list[SearchKnowledgeSourceConfig] = []
        match_details: list[dict[str, Any]] = []
        for source in configured_sources:
            matched_terms = self._matched_routing_terms(question_lower, tokens, source)
            if matched_terms:
                matched_sources.append(source)
            match_details.append(
                {
                    "knowledge_source_name": source.knowledge_source_name,
                    "index_name": source.index_name,
                    "matched_terms": matched_terms,
                }
            )
        diagnostics["knowledge_source_match_details"] = match_details

        if cross_source_intent:
            selected = configured_sources
            diagnostics.update(
                {
                    "routing_mode": "cross_source_intent",
                    "routing_reason": "The question contains compare or cross-source language, so all configured indexes were included.",
                }
            )
        elif matched_sources:
            selected = matched_sources
            diagnostics.update(
                {
                    "routing_mode": "keyword_routed",
                    "routing_reason": "The question matched source routing hints or published corpus terms, so those indexes were selected.",
                }
            )
        elif len(configured_sources) <= settings.azure_search_auto_broadcast_limit:
            selected = configured_sources
            diagnostics.update(
                {
                    "routing_mode": "broad_auto",
                    "routing_reason": (
                        "No source-specific hint matched, so the app broadcast the query across all configured indexes "
                        f"because the source count is within the auto-broadcast limit of {settings.azure_search_auto_broadcast_limit}."
                    ),
                }
            )
        else:
            selected = [self._primary_knowledge_source()]
            diagnostics.update(
                {
                    "routing_mode": "primary_default",
                    "routing_reason": "No source-specific hint matched and the source count exceeds the broadcast limit, so the query stayed on the primary application index.",
                }
            )

        diagnostics["selected_knowledge_sources"] = [source.knowledge_source_name for source in selected]
        diagnostics["selected_search_indexes"] = [source.index_name for source in selected]
        diagnostics["multi_index_routing"] = len(selected) > 1
        return selected, diagnostics

    def _select_target_source_for_document(
        self, *, source_name: str | None = None, route_text: str | None = None
    ) -> tuple[SearchKnowledgeSourceConfig, dict[str, Any]]:
        primary = self._primary_knowledge_source()
        extra_sources = [
            source
            for source in self._configured_knowledge_sources()
            if source.knowledge_source_name != primary.knowledge_source_name
        ]
        source_name_text = (source_name or "").lower()
        route_text_value = (route_text or "").lower()
        combined_text = " ".join(part for part in [source_name_text, route_text_value] if part).strip()
        if not combined_text or not extra_sources:
            return primary, {
                "assignment_mode": "primary_default",
                "assignment_matches": [],
            }

        tokens = self._tokenize_routing_text(combined_text)
        source_name_tokens = self._tokenize_routing_text(source_name_text)
        best_source = primary
        best_matches: list[str] = []
        best_score = 0
        for source in extra_sources:
            name_matches = self._matched_assignment_terms(source_name_text, source_name_tokens, source)
            context_matches = self._matched_assignment_terms(combined_text, tokens, source)
            score = (len(name_matches) * 3) + len(context_matches)
            eligible = bool(name_matches) or len(context_matches) >= 2
            if eligible and score > best_score:
                best_source = source
                best_matches = name_matches or context_matches
                best_score = score

        if best_source == primary:
            return primary, {
                "assignment_mode": "primary_default",
                "assignment_matches": [],
            }
        return best_source, {
            "assignment_mode": "keyword_assigned",
            "assignment_matches": best_matches,
        }

    def _group_doc_ids_by_source(
        self, doc_ids: list[str], doc_source_assignments: dict[str, str]
    ) -> dict[str, list[str]]:
        primary_source_name = settings.azure_search_knowledge_source_name
        grouped: dict[str, list[str]] = {}
        for doc_id in doc_ids:
            source_name = doc_source_assignments.get(doc_id) or primary_source_name
            grouped.setdefault(source_name, []).append(doc_id)
        return grouped

    def _build_retrieve_payload(
        self, question: str, knowledge_source_params: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if self._is_preview_api and settings.azure_search_llm_enabled:
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": question,
                            }
                        ],
                    }
                ],
                "maxRuntimeInSeconds": 20,
                "maxOutputSize": 100000,
                "includeActivity": True,
                "outputMode": "extractiveData",
                "retrievalReasoningEffort": {"kind": settings.azure_search_llm_reasoning_effort},
                "knowledgeSourceParams": knowledge_source_params,
            }
        return {
            "intents": [
                {
                    "type": "semantic",
                    "search": question,
                }
            ],
            "maxRuntimeInSeconds": 20,
            "includeActivity": True,
            "knowledgeSourceParams": knowledge_source_params,
        }

    def _tokenize_routing_text(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]{3,}", text.lower())
            if token not in ROUTING_STOPWORDS
        }

    def _has_cross_source_intent(self, question_lower: str, tokens: set[str]) -> bool:
        compare_tokens = {
            "across",
            "between",
            "both",
            "combine",
            "combined",
            "compare",
            "comparison",
            "contradict",
            "contradiction",
            "cross",
            "different",
            "difference",
            "synthesize",
            "versus",
        }
        compare_phrases = (
            "side by side",
            "compare with",
            "compare across",
            "use both",
            "use all",
            "across the indexes",
            "across indexes",
            "across sources",
        )
        if tokens & compare_tokens:
            return True
        return any(phrase in question_lower for phrase in compare_phrases)

    def _matched_routing_terms(
        self, question_lower: str, tokens: set[str], source: SearchKnowledgeSourceConfig
    ) -> list[str]:
        matches: list[str] = []
        for keyword in source.route_keywords:
            if (" " in keyword and keyword in question_lower) or keyword in tokens:
                matches.append(keyword)

        for label in (source.knowledge_source_name, source.index_name):
            normalized = label.lower().replace("_", " ").replace("-", " ").strip()
            if normalized and normalized in question_lower:
                matches.append(normalized)

        descriptor_terms = self._descriptor_terms_for_source(source)
        descriptor_hits = [
            term
            for term in sorted(tokens & descriptor_terms)
            if len(term) >= 5
        ]
        if descriptor_hits:
            matches.extend(descriptor_hits[:4])

        document_hits = [
            term
            for term in sorted(tokens & self._published_document_terms_for_source(source.knowledge_source_name))
            if len(term) >= 5
        ]
        if document_hits:
            matches.extend(document_hits[:4])

        unique_matches: list[str] = []
        seen: set[str] = set()
        for match in matches:
            if match in seen:
                continue
            seen.add(match)
            unique_matches.append(match)
        return unique_matches

    def _descriptor_terms_for_source(self, source: SearchKnowledgeSourceConfig) -> set[str]:
        descriptor = " ".join(
            filter(None, [source.knowledge_source_name, source.index_name, source.description])
        ).lower()
        return {
            term
            for term in re.findall(r"[a-z0-9]{3,}", descriptor)
            if term not in ROUTING_STOPWORDS
        }

    def _matched_assignment_terms(
        self, document_text: str, tokens: set[str], source: SearchKnowledgeSourceConfig
    ) -> list[str]:
        matches: list[str] = []
        assignment_keywords = source.assignment_keywords or source.route_keywords
        for keyword in assignment_keywords:
            if (" " in keyword and keyword in document_text) or keyword in tokens:
                matches.append(keyword)

        unique_matches: list[str] = []
        seen: set[str] = set()
        for match in matches:
            if match in seen:
                continue
            seen.add(match)
            unique_matches.append(match)
        return unique_matches

    def _published_document_terms_for_source(self, knowledge_source_name: str) -> set[str]:
        from backend.services.job_store import job_store

        terms: set[str] = set()
        for job in job_store.list_jobs():
            if job.status.value != "ready":
                continue
            publish_diagnostics = job.publish_status.diagnostics or {}
            source_name = publish_diagnostics.get("knowledge_source_name") or settings.azure_search_knowledge_source_name
            if source_name != knowledge_source_name:
                continue
            terms.update(self._tokenize_routing_text(job.file_name))
        return terms

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            if detail:
                raise RuntimeError(
                    f"{response.status_code} {response.reason} from Azure AI Search: {detail}"
                ) from exc
            raise


def build_foundry_adapter() -> FoundryIQAdapter:
    if settings.azure_search_enabled:
        return AzureSearchKnowledgeBaseAdapter()
    return LocalPreviewAdapter()
