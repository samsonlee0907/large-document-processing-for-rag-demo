from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from backend.core.config import settings
from backend.domain.models import ChunkRecord, PublishStatus

logger = logging.getLogger(__name__)


class FoundryIQAdapter:
    def publish(self, chunks: list[ChunkRecord]) -> PublishStatus:
        raise NotImplementedError

    def get_status(self) -> PublishStatus:
        raise NotImplementedError

    def chat(self, question: str, *, doc_ids: list[str] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def delete_chunks(self, chunks: list[ChunkRecord]) -> None:
        raise NotImplementedError


class LocalPreviewAdapter(FoundryIQAdapter):
    def publish(self, chunks: list[ChunkRecord]) -> PublishStatus:
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

    def chat(self, question: str, *, doc_ids: list[str] | None = None) -> dict[str, Any]:
        return {
            "answer": "Azure Search is not configured. Local preview mode can only answer over ingested chunks stored in the app.",
            "citations": [],
            "diagnostics": {"mode": "local_preview", "question": question, "selected_doc_ids": doc_ids or []},
        }

    def delete_chunks(self, chunks: list[ChunkRecord]) -> None:
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

    def publish(self, chunks: list[ChunkRecord]) -> PublishStatus:
        self._ensure_index()
        self._upload_chunks(chunks)
        if self.api_version in {"2026-04-01", "2025-11-01-preview"}:
            self._ensure_knowledge_source()
            self._ensure_knowledge_base()
        return PublishStatus(
            mode="search_knowledge_base",
            resource=settings.azure_search_knowledge_base_name,
            ready=True,
            last_sync_time=datetime.now(timezone.utc).isoformat(),
            indexed_document_count=len({chunk.doc_id for chunk in chunks}),
            indexed_chunk_count=len(chunks),
            message="Chunks published to Azure AI Search and associated knowledge base resources ensured.",
            diagnostics={
                "index_name": settings.azure_search_index_name,
                "knowledge_source_name": settings.azure_search_knowledge_source_name,
                "knowledge_base_name": settings.azure_search_knowledge_base_name,
            },
        )

    def get_status(self) -> PublishStatus:
        if not settings.azure_search_enabled:
            return LocalPreviewAdapter().get_status()
        return PublishStatus(
            mode="search_knowledge_base",
            resource=settings.azure_search_knowledge_base_name,
            ready=True,
            message="Azure Search knowledge base publishing is configured.",
            diagnostics={
                "index_name": settings.azure_search_index_name,
                "knowledge_source_name": settings.azure_search_knowledge_source_name,
                "knowledge_base_name": settings.azure_search_knowledge_base_name,
            },
        )

    def chat(self, question: str, *, doc_ids: list[str] | None = None) -> dict[str, Any]:
        knowledge_source_params: dict[str, Any] = {
            "knowledgeSourceName": settings.azure_search_knowledge_source_name,
            "kind": "searchIndex",
            "includeReferences": True,
            "includeReferenceSourceData": True,
        }
        if doc_ids:
            knowledge_source_params["filterAddOn"] = self._build_doc_filter(doc_ids)
        if self._is_preview_api and settings.azure_search_llm_enabled:
            payload: dict[str, Any] = {
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
                "knowledgeSourceParams": [knowledge_source_params],
            }
        else:
            payload = {
                "intents": [
                    {
                        "type": "semantic",
                        "search": question,
                    }
                ],
                "maxRuntimeInSeconds": 20,
                "includeActivity": True,
                "knowledgeSourceParams": [knowledge_source_params],
            }
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
        return result

    def delete_chunks(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return
        url = f"{self.endpoint}/indexes/{settings.azure_search_index_name}/docs/index?api-version=2025-09-01"
        actions = [{"@search.action": "delete", "chunk_id": chunk.chunk_id} for chunk in chunks]
        response = requests.post(url, headers=self.headers, data=json.dumps({"value": actions}), timeout=60)
        self._raise_for_status(response)

    def _ensure_index(self) -> None:
        url = f"{self.endpoint}/indexes/{settings.azure_search_index_name}?api-version=2025-09-01"
        body = {
            "name": settings.azure_search_index_name,
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

    def _upload_chunks(self, chunks: list[ChunkRecord]) -> None:
        url = f"{self.endpoint}/indexes/{settings.azure_search_index_name}/docs/index?api-version=2025-09-01"
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

    def _ensure_knowledge_source(self) -> None:
        url = (
            f"{self.endpoint}/knowledgesources('{settings.azure_search_knowledge_source_name}')"
            f"?api-version={self.api_version}"
        )
        body = {
            "name": settings.azure_search_knowledge_source_name,
            "kind": "searchIndex",
            "searchIndexParameters": {
                "searchIndexName": settings.azure_search_index_name,
                "semanticConfigurationName": "default-semantic-config",
                "sourceDataFields": [
                    {"name": "doc_id"},
                    {"name": "chunk_id"},
                    {"name": "clean_text"},
                    {"name": "source_name"},
                    {"name": "source_uri"},
                    {"name": "section_path"},
                    {"name": "page_numbers"},
                    {"name": "tags"},
                    {"name": "image_evidence_json"},
                ],
                "searchFields": [
                    {"name": "*"},
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
            "knowledgeSources": [{"name": settings.azure_search_knowledge_source_name}],
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
