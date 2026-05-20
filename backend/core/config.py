from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_azure_cli_path() -> str:
    candidate = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd")
    if candidate.exists():
        return str(candidate)
    return "az"


DEFAULT_SEARCH_SOURCE_DATA_FIELDS: tuple[str, ...] = (
    "doc_id",
    "chunk_id",
    "clean_text",
    "source_name",
    "source_uri",
    "section_path",
    "page_numbers",
    "tags",
    "image_evidence_json",
)
DEFAULT_SEARCH_FIELDS: tuple[str, ...] = ("*",)


@dataclass(frozen=True, slots=True)
class SearchKnowledgeSourceConfig:
    knowledge_source_name: str
    index_name: str
    description: str = ""
    route_keywords: tuple[str, ...] = ()
    assignment_keywords: tuple[str, ...] = ()
    semantic_configuration_name: str = "default-semantic-config"
    source_data_fields: tuple[str, ...] = DEFAULT_SEARCH_SOURCE_DATA_FIELDS
    search_fields: tuple[str, ...] = DEFAULT_SEARCH_FIELDS


def _normalize_string_list(value: object, *, lower: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        entry = item.strip()
        if not entry:
            continue
        if lower:
            entry = entry.lower()
        if entry in seen:
            continue
        seen.add(entry)
        normalized.append(entry)
    return tuple(normalized)


def _load_extra_search_sources() -> tuple[SearchKnowledgeSourceConfig, ...]:
    raw = os.getenv("AZURE_SEARCH_EXTRA_SOURCES_JSON", "").strip()
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, list):
        return ()

    sources: list[SearchKnowledgeSourceConfig] = []
    seen_names: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        knowledge_source_name = str(
            item.get("knowledge_source_name") or item.get("name") or ""
        ).strip()
        index_name = str(item.get("index_name") or item.get("search_index_name") or "").strip()
        if not knowledge_source_name or not index_name or knowledge_source_name in seen_names:
            continue
        seen_names.add(knowledge_source_name)
        semantic_configuration_name = str(
            item.get("semantic_configuration_name") or "default-semantic-config"
        ).strip() or "default-semantic-config"
        source_data_fields = _normalize_string_list(item.get("source_data_fields"))
        search_fields = _normalize_string_list(item.get("search_fields"))
        sources.append(
            SearchKnowledgeSourceConfig(
                knowledge_source_name=knowledge_source_name,
                index_name=index_name,
                description=str(item.get("description") or "").strip(),
                route_keywords=_normalize_string_list(item.get("route_keywords"), lower=True),
                assignment_keywords=_normalize_string_list(
                    item.get("assignment_keywords") or item.get("document_keywords"),
                    lower=True,
                ),
                semantic_configuration_name=semantic_configuration_name,
                source_data_fields=source_data_fields or DEFAULT_SEARCH_SOURCE_DATA_FIELDS,
                search_fields=search_fields or DEFAULT_SEARCH_FIELDS,
            )
        )
    return tuple(sources)


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Enterprise Knowledge Ingestion")
    environment: str = os.getenv("APP_ENV", "development")
    base_dir: Path = Path(os.getenv("APP_BASE_DIR", Path.cwd()))
    data_dir: Path = Path(os.getenv("APP_DATA_DIR", Path.cwd() / "data"))
    uploads_dir: Path = Path(os.getenv("APP_UPLOADS_DIR", Path.cwd() / "data" / "uploads"))
    artifacts_dir: Path = Path(os.getenv("APP_ARTIFACTS_DIR", Path.cwd() / "data" / "artifacts"))
    store_path: Path = Path(os.getenv("APP_STORE_PATH", Path.cwd() / "data" / "job_store.json"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    chunk_size_tokens: int = int(os.getenv("CHUNK_SIZE_TOKENS", "420"))
    chunk_overlap_tokens: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "60"))
    max_pages_per_segment: int = int(os.getenv("MAX_PAGES_PER_SEGMENT", "250"))
    large_document_page_threshold: int = int(os.getenv("LARGE_DOCUMENT_PAGE_THRESHOLD", "250"))
    hard_page_split_threshold: int = int(os.getenv("HARD_PAGE_SPLIT_THRESHOLD", "2000"))
    hard_file_split_threshold_mb: int = int(os.getenv("HARD_FILE_SPLIT_THRESHOLD_MB", "500"))
    use_semantic_chunking: bool = _env_flag("USE_SEMANTIC_CHUNKING", False)
    enable_demo_seed: bool = _env_flag("ENABLE_DEMO_SEED", True)
    azure_cli_path: str = os.getenv("AZURE_CLI_PATH", _default_azure_cli_path())
    azure_document_intelligence_endpoint: str = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    azure_document_intelligence_key: str = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    azure_document_intelligence_model: str = os.getenv(
        "AZURE_DOCUMENT_INTELLIGENCE_MODEL", "prebuilt-layout"
    )
    azure_content_understanding_endpoint: str = os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT", "")
    azure_content_understanding_key: str = os.getenv("AZURE_CONTENT_UNDERSTANDING_KEY", "")
    azure_content_understanding_analyzer_id: str = os.getenv(
        "AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID", ""
    )
    azure_search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    azure_search_key: str = os.getenv("AZURE_SEARCH_KEY", "")
    azure_search_index_name: str = os.getenv("AZURE_SEARCH_INDEX_NAME", "enterprise-knowledge-index")
    azure_search_knowledge_source_name: str = os.getenv(
        "AZURE_SEARCH_KNOWLEDGE_SOURCE_NAME", "enterprise-knowledge-source"
    )
    azure_search_knowledge_base_name: str = os.getenv(
        "AZURE_SEARCH_KNOWLEDGE_BASE_NAME", "enterprise-knowledge-base"
    )
    azure_search_api_version: str = os.getenv("AZURE_SEARCH_API_VERSION", "2026-04-01")
    azure_search_extra_sources: tuple[SearchKnowledgeSourceConfig, ...] = _load_extra_search_sources()
    azure_search_auto_broadcast_limit: int = int(os.getenv("AZURE_SEARCH_AUTO_BROADCAST_LIMIT", "4"))
    azure_openai_embedding_deployment: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
    azure_foundry_resource_endpoint: str = os.getenv("AZURE_FOUNDRY_RESOURCE_ENDPOINT", "")
    azure_foundry_api_key: str = os.getenv("AZURE_FOUNDRY_API_KEY", "")
    azure_foundry_chat_deployment: str = os.getenv("AZURE_FOUNDRY_CHAT_DEPLOYMENT", "")
    azure_foundry_project_endpoint: str = os.getenv("AZURE_FOUNDRY_PROJECT_ENDPOINT", "")
    azure_foundry_agent_id: str = os.getenv("AZURE_FOUNDRY_AGENT_ID", "")
    foundry_chat_mode: str = os.getenv("FOUNDRY_CHAT_MODE", "search_knowledge_base")
    azure_search_llm_deployment: str = os.getenv("AZURE_SEARCH_LLM_DEPLOYMENT", "")
    azure_search_llm_model_name: str = os.getenv("AZURE_SEARCH_LLM_MODEL_NAME", "")
    azure_search_llm_reasoning_effort: str = os.getenv("AZURE_SEARCH_LLM_REASONING_EFFORT", "low")
    azure_search_llm_use_managed_identity: bool = _env_flag("AZURE_SEARCH_LLM_USE_MANAGED_IDENTITY", True)
    search_query_key: str = os.getenv("AZURE_SEARCH_QUERY_KEY", "")
    azure_storage_account: str = os.getenv("AZURE_STORAGE_ACCOUNT", "")
    azure_storage_account_key: str = os.getenv("AZURE_STORAGE_ACCOUNT_KEY", "")
    azure_storage_container: str = os.getenv("AZURE_STORAGE_CONTAINER", "document-figure-artifacts")
    enable_image_understanding: bool = _env_flag("ENABLE_IMAGE_UNDERSTANDING", True)
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def azure_docint_enabled(self) -> bool:
        return bool(self.azure_document_intelligence_endpoint and self.azure_document_intelligence_key)

    @property
    def azure_content_understanding_enabled(self) -> bool:
        return bool(
            self.azure_content_understanding_endpoint
            and self.azure_content_understanding_key
            and self.azure_content_understanding_analyzer_id
        )

    @property
    def azure_search_enabled(self) -> bool:
        return bool(self.azure_search_endpoint and self.azure_search_key)

    @property
    def azure_search_multi_index_enabled(self) -> bool:
        return len(self.azure_search_extra_sources) > 0

    @property
    def azure_foundry_chat_enabled(self) -> bool:
        return bool(self.azure_foundry_resource_endpoint and self.azure_foundry_chat_deployment)

    @property
    def azure_search_llm_enabled(self) -> bool:
        return bool(
            self.azure_search_llm_deployment
            and self.azure_foundry_openai_base_url
            and (self.azure_search_llm_use_managed_identity or self.azure_foundry_api_key)
        )

    @property
    def azure_foundry_openai_base_url(self) -> str:
        if not self.azure_foundry_resource_endpoint:
            return ""
        parsed = urlparse(self.azure_foundry_resource_endpoint)
        hostname = parsed.netloc
        if hostname.endswith(".cognitiveservices.azure.com"):
            hostname = hostname.replace(".cognitiveservices.azure.com", ".openai.azure.com")
        if not hostname:
            return ""
        scheme = parsed.scheme or "https"
        return f"{scheme}://{hostname}"

    @property
    def azure_blob_storage_enabled(self) -> bool:
        return bool(self.azure_storage_account and self.azure_storage_container)

    @property
    def azure_blob_account_url(self) -> str:
        if not self.azure_storage_account:
            return ""
        return f"https://{self.azure_storage_account}.blob.core.windows.net"

    @property
    def hard_file_split_threshold_bytes(self) -> int:
        return self.hard_file_split_threshold_mb * 1024 * 1024


settings = Settings()
settings.ensure_directories()
