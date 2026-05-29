from __future__ import annotations

import csv
import json
import logging
import re
import subprocess
import uuid
from dataclasses import dataclass
from math import sqrt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep

import requests

from backend.core.config import settings
from backend.domain.models import IntermediateDocument, SectionNode
from backend.services.blob_storage import build_blob_artifact_store
from backend.services.foundry_openai import describe_image_with_foundry

logger = logging.getLogger(__name__)

try:
    from pypdf import PdfReader, PdfWriter
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None  # type: ignore[assignment]
    PdfWriter = None  # type: ignore[assignment]

try:
    import docx  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    docx = None  # type: ignore[assignment]

try:
    from PIL import Image as PILImage
except Exception:  # pragma: no cover - optional dependency
    PILImage = None  # type: ignore[assignment]


@dataclass(slots=True)
class DocumentProfile:
    format: str
    complexity: str
    page_count: int | None
    parser_path: str
    warnings: list[str]


@dataclass(slots=True)
class PdfSegment:
    path: Path
    page_start: int
    page_end: int


@dataclass(slots=True)
class ParagraphBlock:
    text: str
    page_start: int | None = None
    page_end: int | None = None


def _resampling_filter() -> object:
    if PILImage is None:
        raise RuntimeError("Pillow is required for image normalization.")
    resampling = getattr(PILImage, "Resampling", PILImage)
    return resampling.LANCZOS


def _normalize_figure_image(
    image: object,
    artifact_base: Path,
) -> tuple[Path, dict[str, object]]:
    original_name = str(getattr(image, "name", artifact_base.name))
    original_suffix = Path(original_name).suffix.lower() or ".bin"
    metadata: dict[str, object] = {"original_image_name": original_name}

    pil_image = getattr(image, "image", None)
    if PILImage is None or pil_image is None:
        artifact_path = artifact_base.with_suffix(original_suffix)
        artifact_path.write_bytes(getattr(image, "data", b""))
        metadata["normalized_image"] = False
        metadata["output_format"] = original_suffix.lstrip(".")
        return artifact_path, metadata

    normalized = pil_image.copy()
    width, height = normalized.size
    metadata["original_width"] = width
    metadata["original_height"] = height
    pixel_count = width * height
    metadata["original_pixel_count"] = pixel_count

    scale_candidates = [1.0]
    if settings.max_figure_image_pixels > 0 and pixel_count > settings.max_figure_image_pixels:
        scale_candidates.append(sqrt(settings.max_figure_image_pixels / pixel_count))
    if settings.max_figure_image_dimension > 0:
        largest_dimension = max(width, height)
        if largest_dimension > settings.max_figure_image_dimension:
            scale_candidates.append(settings.max_figure_image_dimension / largest_dimension)
    scale = min(scale_candidates)
    if scale < 1.0:
        resized_width = max(1, int(width * scale))
        resized_height = max(1, int(height * scale))
        normalized = normalized.resize((resized_width, resized_height), _resampling_filter())
        metadata["resized_width"] = resized_width
        metadata["resized_height"] = resized_height
    else:
        metadata["resized_width"] = width
        metadata["resized_height"] = height

    if normalized.mode not in {"RGB", "RGBA"}:
        normalized = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")
    output_format = "PNG"
    artifact_path = artifact_base.with_suffix(".png")
    normalized.save(artifact_path, format=output_format, optimize=True)
    metadata["normalized_image"] = True
    metadata["output_format"] = output_format.lower()
    metadata["artifact_pixel_count"] = metadata["resized_width"] * metadata["resized_height"]
    metadata["downscaled"] = bool(scale < 1.0)
    return artifact_path, metadata


def _extract_pdf_figure_artifacts(path: Path, doc_id: str, source_name: str) -> list[dict[str, object]]:
    if PdfReader is None:
        return []
    try:
        reader = PdfReader(str(path))
    except Exception:
        return []

    figure_dir = settings.artifacts_dir / f"{doc_id}_figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    blob_store = build_blob_artifact_store()
    figures: list[dict[str, object]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_images = getattr(page, "images", None)
        if page_images is None:
            continue
        try:
            image_ids = list(page_images.keys())
        except Exception as exc:
            logger.warning(
                "page image enumeration failed",
                extra={"context": {"source": source_name, "page_number": page_number, "error": str(exc)}},
            )
            continue
        for image_index, image_id in enumerate(image_ids, start=1):
            try:
                image = page_images[image_id]
            except Exception as exc:
                logger.warning(
                    "skipping PDF figure image",
                    extra={
                        "context": {
                            "source": source_name,
                            "page_number": page_number,
                            "image_index": image_index,
                            "image_id": image_id if isinstance(image_id, str) else str(image_id),
                            "error": str(exc),
                        }
                    },
                )
                continue
            artifact_base = figure_dir / f"page_{page_number:04d}_figure_{image_index}"
            try:
                artifact_path, image_metadata = _normalize_figure_image(image, artifact_base)
            except Exception:
                continue
            artifact_id = uuid.uuid4().hex[:12]
            figure: dict[str, object] = {
                "artifact_id": artifact_id,
                "page_number": page_number,
                "image_name": getattr(image, "name", f"figure_{image_index}{artifact_path.suffix}"),
                "artifact_path": str(artifact_path),
            }
            figure.update(image_metadata)
            if blob_store is not None:
                blob_name = f"documents/{doc_id}/figures/{artifact_path.name}"
                try:
                    upload_result = blob_store.upload_file(
                        artifact_path,
                        blob_name=blob_name,
                        metadata={
                            "docid": doc_id,
                            "source": source_name[:120],
                            "page": str(page_number),
                        },
                    )
                    figure.update(upload_result)
                except Exception as exc:
                    logger.warning(
                        "blob upload failed for figure artifact",
                        extra={"context": {"artifact_path": str(artifact_path), "error": str(exc)}},
                    )
                    figure["blob_upload_error"] = str(exc)
            if settings.enable_image_understanding and settings.azure_foundry_chat_enabled:
                try:
                    description, model_endpoint = describe_image_with_foundry(
                        artifact_path,
                        source_name=source_name,
                        page_number=page_number,
                    )
                    figure["description"] = description
                    figure["description_model_endpoint"] = model_endpoint
                except Exception as exc:
                    logger.warning("image description failed", extra={"context": {"artifact_path": str(artifact_path), "error": str(exc)}})
                    figure["description_error"] = str(exc)
            figures.append(figure)
    return figures


class ParserSelection:
    def profile(self, path: Path) -> DocumentProfile:
        suffix = path.suffix.lower()
        warnings: list[str] = []
        if suffix in {".txt", ".md", ".json", ".csv"}:
            return DocumentProfile(suffix.lstrip("."), "simple", 1, "local_simple_parser", warnings)
        if suffix in {".pdf"}:
            page_count = self._pdf_page_count(path)
            file_size_bytes = self._file_size_bytes(path)
            complexity = "complex" if (page_count or 0) > 10 else "moderate"
            split_reasons: list[str] = []
            if page_count and page_count > settings.hard_page_split_threshold:
                split_reasons.append(f"{settings.hard_page_split_threshold} pages")
            if file_size_bytes > settings.hard_file_split_threshold_bytes:
                split_reasons.append(f"{settings.hard_file_split_threshold_mb} MB")
            if split_reasons:
                warnings.append(
                    "PDF exceeds the segmentation threshold "
                    + " and ".join(split_reasons)
                    + " and will be segmented before analysis."
                )
            parser_path = "azure_document_intelligence" if settings.azure_docint_enabled else "fallback_pdf_stub"
            return DocumentProfile("pdf", complexity, page_count, parser_path, warnings)
        if suffix in {".docx", ".pptx", ".xlsx"}:
            parser_path = (
                "azure_content_understanding"
                if settings.azure_content_understanding_enabled
                else "azure_document_intelligence"
                if settings.azure_docint_enabled
                else "local_office_stub"
            )
            return DocumentProfile(suffix.lstrip("."), "moderate", None, parser_path, warnings)
        return DocumentProfile("binary", "unknown", None, "unsupported_fallback", ["Format not fully supported"])

    def _pdf_page_count(self, path: Path) -> int | None:
        if PdfReader is None:
            return None
        try:
            reader = PdfReader(str(path))
            return len(reader.pages)
        except Exception:
            return None

    def _file_size_bytes(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except Exception:
            return 0


class BaseParser:
    parser_path = "base"

    def parse(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        raise NotImplementedError


class AzureCognitiveAuthMixin:
    _token_cache: dict[str, tuple[str, datetime]] = {}

    def _build_cognitive_headers(
        self,
        api_key: str,
        *,
        content_type: str | None = None,
        prefer_aad: bool = False,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        if api_key and not prefer_aad:
            headers["Ocp-Apim-Subscription-Key"] = api_key
            return headers
        headers["Authorization"] = f"Bearer {self._get_cognitive_services_token()}"
        return headers

    def _retry_with_aad(self, response: requests.Response, prefer_aad: bool) -> bool:
        return response.status_code in {401, 403} and not prefer_aad

    def _get_cognitive_services_token(self) -> str:
        cached = self._token_cache.get("cognitiveservices")
        now = datetime.now(timezone.utc)
        if cached and cached[1] > now + timedelta(minutes=5):
            return cached[0]

        result = subprocess.run(
            [
                settings.azure_cli_path,
                "account",
                "get-access-token",
                "--resource",
                "https://cognitiveservices.azure.com/",
                "--output",
                "json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        token = payload["accessToken"]
        expires_on_epoch = payload.get("expires_on")
        expires_on = payload.get("expiresOn")
        if expires_on_epoch:
            expires_at = datetime.fromtimestamp(int(expires_on_epoch), tz=timezone.utc)
        elif expires_on:
            parsed = datetime.fromisoformat(expires_on.replace("Z", "+00:00"))
            expires_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        else:
            expires_at = now + timedelta(minutes=50)
        self._token_cache["cognitiveservices"] = (token, expires_at)
        return token


class LocalSimpleParser(BaseParser):
    parser_path = "local_simple_parser"

    def parse(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return self._parse_csv(path, doc_id, profile)
        if suffix == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(raw, indent=2)
        elif suffix == ".md":
            text = path.read_text(encoding="utf-8")
            return self._parse_markdown(path, doc_id, profile, text)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
        return IntermediateDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            parser_path=self.parser_path,
            page_count=profile.page_count,
            sections=[SectionNode(heading="Document", paragraphs=[text])],
            warnings=profile.warnings,
        )

    def _parse_markdown(
        self, path: Path, doc_id: str, profile: DocumentProfile, text: str
    ) -> IntermediateDocument:
        root_sections: list[SectionNode] = []
        current = SectionNode(heading="Introduction", level=1)
        for line in text.splitlines():
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
            if heading_match:
                if current.paragraphs or current.heading != "Introduction":
                    root_sections.append(current)
                current = SectionNode(
                    heading=heading_match.group(2).strip(),
                    level=len(heading_match.group(1)),
                )
                continue
            if line.strip():
                current.paragraphs.append(line.strip())
        if current.paragraphs or current.heading != "Introduction":
            root_sections.append(current)
        return IntermediateDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            parser_path=self.parser_path,
            page_count=profile.page_count,
            sections=root_sections or [SectionNode(heading="Document", paragraphs=[text])],
            warnings=profile.warnings,
        )

    def _parse_csv(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            rows = [row for row in reader]
        heading = rows[0] if rows else ["Columns"]
        body = rows[1:] if len(rows) > 1 else []
        return IntermediateDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            parser_path=self.parser_path,
            page_count=profile.page_count,
            sections=[
                SectionNode(
                    heading=f"CSV:{' / '.join(heading)}",
                    paragraphs=[],
                    tables=[body],
                )
            ],
            warnings=profile.warnings,
        )


class LocalOfficeParser(BaseParser):
    parser_path = "local_office_stub"

    def parse(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        sections: list[SectionNode] = []
        warnings = list(profile.warnings)
        if path.suffix.lower() == ".docx" and docx is not None:
            doc = docx.Document(str(path))
            paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
            sections.append(SectionNode(heading="Word Document", paragraphs=paragraphs))
        else:
            warnings.append(
                "Local Office parsing is limited. Configure Azure Content Understanding or Document Intelligence."
            )
            sections.append(
                SectionNode(
                    heading="Office Document",
                    paragraphs=[
                        "This document type requires Azure parsing for production extraction fidelity.",
                        f"File: {path.name}",
                    ],
                )
            )
        return IntermediateDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            parser_path=self.parser_path,
            page_count=profile.page_count,
            sections=sections,
            warnings=warnings,
        )


class AzureDocumentIntelligenceParser(AzureCognitiveAuthMixin, BaseParser):
    parser_path = "azure_document_intelligence"

    def parse(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        if not settings.azure_docint_enabled:
            return LocalOfficeParser().parse(path, doc_id, profile)

        warnings = list(profile.warnings)
        metadata = {"model_id": settings.azure_document_intelligence_model}
        figure_sections = self._figure_sections(path, doc_id, metadata)
        if path.suffix.lower() == ".pdf" and self._should_split_pdf(path, profile):
            segment_size = self._recommended_segment_size(path, profile)
            segments = self._split_pdf(path, segment_size)
            sections: list[SectionNode] = []
            for segment in segments:
                result = self._analyze_document_result(segment.path)
                paragraphs = self._extract_paragraph_blocks(
                    result,
                    page_offset=segment.page_start - 1,
                )
                segment_sections = self._build_structured_sections(
                    paragraphs or [ParagraphBlock("No content returned.", segment.page_start, segment.page_end)],
                    f"Pages {segment.page_start}-{segment.page_end}",
                )
                sections.extend(segment_sections)
            metadata["segment_count"] = len(segments)
            metadata["segment_page_ranges"] = [
                {"page_start": segment.page_start, "page_end": segment.page_end} for segment in segments
            ]
            metadata["segmentation_strategy"] = "pdf_page_segmentation"
            metadata["segmentation_triggers"] = self._segmentation_triggers(path, profile)
            metadata["segment_size_pages"] = segment_size
            warnings.append(
                f"PDF was split into {len(segments)} segments of up to {segment_size} pages before analysis."
            )
        else:
            sections = self._analyze_document(path, profile)
        sections.extend(figure_sections)
        return IntermediateDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            parser_path=self.parser_path,
            page_count=profile.page_count,
            sections=sections or [SectionNode(heading="Document", paragraphs=["No content returned."])],
            warnings=warnings,
            metadata=metadata,
        )

    def _file_size_bytes(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except Exception:
            return 0

    def _segmentation_triggers(self, path: Path, profile: DocumentProfile) -> list[str]:
        triggers: list[str] = []
        if profile.page_count and profile.page_count > settings.hard_page_split_threshold:
            triggers.append("page_count")
        if self._file_size_bytes(path) > settings.hard_file_split_threshold_bytes:
            triggers.append("file_size")
        return triggers

    def _should_split_pdf(self, path: Path, profile: DocumentProfile) -> bool:
        return bool(self._segmentation_triggers(path, profile))

    def _recommended_segment_size(self, path: Path, profile: DocumentProfile) -> int:
        page_limit_segment_size = settings.max_pages_per_segment
        file_size_bytes = self._file_size_bytes(path)
        if not profile.page_count or file_size_bytes <= settings.hard_file_split_threshold_bytes:
            return page_limit_segment_size

        required_segments_by_size = max(
            1,
            -(-file_size_bytes // settings.hard_file_split_threshold_bytes),
        )
        size_based_segment_size = max(1, -(-profile.page_count // required_segments_by_size))
        return min(page_limit_segment_size, size_based_segment_size)

    def _figure_sections(self, path: Path, doc_id: str, metadata: dict[str, object]) -> list[SectionNode]:
        if path.suffix.lower() != ".pdf":
            return []
        figures = _extract_pdf_figure_artifacts(path, doc_id, path.name)
        if not figures:
            return []
        metadata["figure_count"] = len(figures)
        metadata["figure_artifacts"] = figures
        paragraphs = [
            (
                f"Figure extracted from page {figure['page_number']}: {figure['image_name']} | "
                f"artifact: {figure['artifact_path']}"
                + (f" | description: {figure['description']}" if figure.get("description") else "")
            )
            for figure in figures
        ]
        return [SectionNode(heading="Extracted Figures", level=1, paragraphs=paragraphs)]

    def _analyze_document(self, path: Path, profile: DocumentProfile) -> list[SectionNode]:
        result = self._analyze_document_result(path)
        paragraphs = self._extract_paragraph_blocks(result)
        return self._build_structured_sections(
            paragraphs or [ParagraphBlock("No content returned.")],
            "Layout Extraction",
        )

    def _analyze_document_result(self, path: Path) -> dict:
        url = (
            f"{settings.azure_document_intelligence_endpoint.rstrip('/')}"
            f"/documentintelligence/documentModels/{settings.azure_document_intelligence_model}:analyze"
            "?api-version=2024-11-30"
        )
        prefer_aad = False
        body = path.read_bytes()
        headers = self._build_cognitive_headers(
            settings.azure_document_intelligence_key,
            content_type="application/octet-stream",
            prefer_aad=prefer_aad,
        )
        response = requests.post(
            url,
            headers=headers,
            data=body,
            timeout=settings.request_timeout_seconds,
        )
        if self._retry_with_aad(response, prefer_aad):
            prefer_aad = True
            headers = self._build_cognitive_headers(
                settings.azure_document_intelligence_key,
                content_type="application/octet-stream",
                prefer_aad=True,
            )
            response = requests.post(
                url,
                headers=headers,
                data=body,
                timeout=settings.request_timeout_seconds,
            )
        response.raise_for_status()
        operation_location = response.headers.get("Operation-Location")
        if operation_location:
            result = self._poll_operation(operation_location, headers)
        else:
            result = response.json()
        return result

    def _extract_paragraphs(self, result: dict) -> list[str]:
        paragraphs: list[str] = []
        for paragraph in result.get("paragraphs", []):
            content = paragraph.get("content", "").strip()
            if content:
                paragraphs.append(content)
        if not paragraphs and result.get("content"):
            paragraphs = [result["content"]]
        return paragraphs

    def _extract_paragraph_blocks(self, result: dict, *, page_offset: int = 0) -> list[ParagraphBlock]:
        blocks: list[ParagraphBlock] = []
        for paragraph in result.get("paragraphs", []):
            content = paragraph.get("content", "").strip()
            if not content:
                continue
            page_numbers: list[int] = []
            for region in paragraph.get("boundingRegions") or []:
                page_number = region.get("pageNumber")
                if isinstance(page_number, int):
                    page_numbers.append(page_number + page_offset)
            blocks.append(
                ParagraphBlock(
                    text=content,
                    page_start=min(page_numbers) if page_numbers else None,
                    page_end=max(page_numbers) if page_numbers else None,
                )
            )
        if not blocks and result.get("content"):
            blocks.append(ParagraphBlock(text=str(result["content"]).strip()))
        return blocks

    def _build_structured_sections(
        self,
        paragraphs: list[ParagraphBlock],
        default_heading: str,
    ) -> list[SectionNode]:
        sections: list[SectionNode] = []
        preamble: list[ParagraphBlock] = []
        current: SectionNode | None = None
        for paragraph in paragraphs:
            heading_match = re.match(r"^Section\s+(\d+)[\.\-:]\s+(.*)$", paragraph.text)
            if heading_match:
                normalized_heading = f"Section {heading_match.group(1)}. {heading_match.group(2).strip()}"
                if current is not None and (
                    current.heading == normalized_heading
                    or normalized_heading.startswith(current.heading)
                    or current.heading.startswith(normalized_heading)
                ):
                    continue
                if current is not None:
                    sections.append(current)
                current = SectionNode(
                    heading=normalized_heading,
                    level=1,
                    paragraphs=[],
                    page_start=paragraph.page_start,
                    page_end=paragraph.page_end,
                )
                continue
            if current is None:
                preamble.append(paragraph)
            else:
                current.paragraphs.append(paragraph.text)
                current.page_start = min(
                    [value for value in [current.page_start, paragraph.page_start] if value is not None],
                    default=current.page_start,
                )
                current.page_end = max(
                    [value for value in [current.page_end, paragraph.page_end] if value is not None],
                    default=current.page_end,
                )
        if current is not None:
            sections.append(current)
        if sections:
            if preamble:
                preamble_page_starts = [block.page_start for block in preamble if block.page_start is not None]
                preamble_page_ends = [block.page_end for block in preamble if block.page_end is not None]
                sections.insert(
                    0,
                    SectionNode(
                        heading=default_heading,
                        level=1,
                        paragraphs=[block.text for block in preamble],
                        page_start=min(preamble_page_starts) if preamble_page_starts else None,
                        page_end=max(preamble_page_ends) if preamble_page_ends else None,
                    ),
                )
            return sections
        page_starts = [block.page_start for block in paragraphs if block.page_start is not None]
        page_ends = [block.page_end for block in paragraphs if block.page_end is not None]
        return [
            SectionNode(
                heading=default_heading,
                paragraphs=[block.text for block in paragraphs],
                page_start=min(page_starts) if page_starts else None,
                page_end=max(page_ends) if page_ends else None,
            )
        ]

    def _split_pdf(self, path: Path, segment_size: int) -> list[PdfSegment]:
        if PdfReader is None or PdfWriter is None:
            raise RuntimeError("pypdf is required to split oversized PDF files.")

        reader = PdfReader(str(path))
        segment_dir = settings.artifacts_dir / f"{path.stem}_segments"
        segment_dir.mkdir(parents=True, exist_ok=True)

        segments: list[PdfSegment] = []
        total_pages = len(reader.pages)
        for start_index in range(0, total_pages, segment_size):
            end_index = min(start_index + segment_size, total_pages)
            writer = PdfWriter()
            for page_index in range(start_index, end_index):
                writer.add_page(reader.pages[page_index])
            segment_path = segment_dir / f"{path.stem}_pages_{start_index + 1}_{end_index}.pdf"
            with segment_path.open("wb") as handle:
                writer.write(handle)
            segments.append(
                PdfSegment(path=segment_path, page_start=start_index + 1, page_end=end_index)
            )
        return segments

    def _poll_operation(self, operation_location: str, headers: dict[str, str], max_attempts: int = 300) -> dict:
        for _ in range(max_attempts):
            response = requests.get(operation_location, headers=headers, timeout=settings.request_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status", "").lower()
            if status == "succeeded":
                return payload.get("analyzeResult") or payload
            if status == "failed":
                raise RuntimeError(f"Document Intelligence analysis failed: {payload}")
            sleep(1)
        raise TimeoutError("Document Intelligence analysis timed out.")


class AzureContentUnderstandingParser(AzureCognitiveAuthMixin, BaseParser):
    parser_path = "azure_content_understanding"

    def parse(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        if not settings.azure_content_understanding_enabled:
            return AzureDocumentIntelligenceParser().parse(path, doc_id, profile)
        url = (
            f"{settings.azure_content_understanding_endpoint.rstrip('/')}"
            f"/contentunderstanding/analyzers/{settings.azure_content_understanding_analyzer_id}:analyze"
            "?api-version=2025-11-01"
        )
        prefer_aad = False
        headers = self._build_cognitive_headers(
            settings.azure_content_understanding_key,
            prefer_aad=prefer_aad,
        )
        body = path.read_bytes()
        files = {"file": (path.name, body)}
        response = requests.post(url, headers=headers, files=files, timeout=settings.request_timeout_seconds)
        if self._retry_with_aad(response, prefer_aad):
            headers = self._build_cognitive_headers(
                settings.azure_content_understanding_key,
                prefer_aad=True,
            )
            files = {"file": (path.name, body)}
            response = requests.post(url, headers=headers, files=files, timeout=settings.request_timeout_seconds)
        response.raise_for_status()
        operation_location = response.headers.get("Operation-Location")
        if operation_location:
            payload = self._poll_operation(operation_location, headers)
        else:
            payload = response.json()
        extracted = payload.get("result", {}).get("contents", [])
        paragraphs = []
        for item in extracted:
            text = item.get("markdown") or item.get("text") or ""
            if text.strip():
                paragraphs.append(text.strip())
        return IntermediateDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            parser_path=self.parser_path,
            page_count=profile.page_count,
            sections=[SectionNode(heading="Content Understanding", paragraphs=paragraphs)],
            warnings=profile.warnings,
            metadata={"analyzer_id": settings.azure_content_understanding_analyzer_id},
        )

    def _poll_operation(self, operation_location: str, headers: dict[str, str]) -> dict:
        for _ in range(60):
            response = requests.get(operation_location, headers=headers, timeout=settings.request_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status", "").lower()
            if status in {"succeeded", "completed"}:
                return payload
            if status in {"failed", "error"}:
                raise RuntimeError(f"Content Understanding analysis failed: {payload}")
            sleep(1)
        raise TimeoutError("Content Understanding analysis timed out.")


class FallbackPdfParser(BaseParser):
    parser_path = "fallback_pdf_stub"

    def parse(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        warnings = list(profile.warnings)
        warnings.append(
            "PDF parsing fallback is limited. Configure Azure Document Intelligence for layout-aware extraction."
        )
        paragraphs = self._extract_pdf_text(path)
        metadata: dict[str, object] = {}
        figure_sections = self._figure_sections(path, doc_id, metadata)
        sections = [
            SectionNode(
                heading="PDF Fallback",
                paragraphs=paragraphs,
            )
        ]
        sections.extend(figure_sections)
        return IntermediateDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_path=str(path),
            format=profile.format,
            complexity=profile.complexity,
            parser_path=self.parser_path,
            page_count=profile.page_count,
            sections=sections,
            metadata=metadata,
            warnings=warnings,
        )

    def _extract_pdf_text(self, path: Path) -> list[str]:
        paragraphs = [
            "The current environment is not configured for Azure parsing.",
            "The ingestion pipeline still produced chunkable placeholder content and metadata.",
        ]
        if PdfReader is None:
            return paragraphs
        try:
            reader = PdfReader(str(path))
            extracted = []
            for page in reader.pages[:10]:
                text = (page.extract_text() or "").strip()
                if text:
                    extracted.append(text)
            return extracted or paragraphs
        except Exception:
            return paragraphs

    def _figure_sections(self, path: Path, doc_id: str, metadata: dict[str, object]) -> list[SectionNode]:
        figures = _extract_pdf_figure_artifacts(path, doc_id, path.name)
        if not figures:
            return []
        metadata["figure_count"] = len(figures)
        metadata["figure_artifacts"] = figures
        return [
            SectionNode(
                heading="Extracted Figures",
                paragraphs=[
                    f"Figure extracted from page {figure['page_number']}: {figure['image_name']} | artifact: {figure['artifact_path']}"
                    for figure in figures
                ],
            )
        ]


class ParserRegistry:
    def __init__(self) -> None:
        self.selector = ParserSelection()
        self.parsers: dict[str, BaseParser] = {
            "local_simple_parser": LocalSimpleParser(),
            "local_office_stub": LocalOfficeParser(),
            "azure_document_intelligence": AzureDocumentIntelligenceParser(),
            "azure_content_understanding": AzureContentUnderstandingParser(),
            "fallback_pdf_stub": FallbackPdfParser(),
            "unsupported_fallback": LocalOfficeParser(),
        }

    def detect(self, path: Path) -> DocumentProfile:
        return self.selector.profile(path)

    def parse(self, path: Path, doc_id: str, profile: DocumentProfile) -> IntermediateDocument:
        parser = self.parsers[profile.parser_path]
        logger.info("selected parser", extra={"context": {"parser_path": parser.parser_path, "file": path.name}})
        return parser.parse(path, doc_id, profile)


parser_registry = ParserRegistry()
