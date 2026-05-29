from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

import requests

from backend.core.config import settings
from backend.services.azure_auth import AzureCognitiveTokenProvider


def _extract_model_answer(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("GPT-5.4 response did not contain any choices.")

    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
        if texts:
            return "\n".join(texts)
    raise RuntimeError("GPT-5.4 response did not contain readable text.")


def _raise_model_error(response: requests.Response, *, prefix: str = "GPT-5.4") -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        if detail:
            raise RuntimeError(f"{response.status_code} {response.reason} from {prefix}: {detail}") from exc
        raise


def _model_urls() -> list[str]:
    base_url = settings.azure_foundry_openai_base_url.rstrip("/")
    return [
        f"{base_url}/openai/v1/chat/completions",
        (
            f"{base_url}/openai/deployments/{settings.azure_foundry_chat_deployment}/chat/completions"
            f"?api-version=2024-10-21"
        ),
    ]


def _send_chat_completion(body: dict[str, Any]) -> tuple[str, str]:
    token = AzureCognitiveTokenProvider.get_bearer_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    timeout = min(settings.request_timeout_seconds, 45)
    last_error: RuntimeError | None = None
    for url in _model_urls():
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        if response.ok:
            return _extract_model_answer(response.json()), url
        if response.status_code in {400, 404, 405}:
            last_error = RuntimeError(
                f"{response.status_code} {response.reason} from model endpoint {url}: {response.text.strip()}"
            )
            continue
        _raise_model_error(response)
    if last_error:
        raise last_error
    raise RuntimeError("GPT-5.4 request failed before a response was returned.")


def call_foundry_text(messages: list[dict[str, Any]], *, max_completion_tokens: int = 900) -> tuple[str, str]:
    body = {
        "model": settings.azure_foundry_chat_deployment,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
    }
    return _send_chat_completion(body)


def _image_data_url(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def describe_image_with_foundry(
    image_path: Path,
    *,
    source_name: str,
    page_number: int | None = None,
) -> tuple[str, str]:
    if not settings.azure_foundry_chat_enabled:
        raise RuntimeError("GPT-5.4 image understanding is not configured.")

    page_context = f" from page {page_number}" if page_number is not None else ""
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are describing an extracted document figure for enterprise retrieval. "
                "Return a concise description of what the figure shows, the likely chart or diagram type, "
                "and the key business or technical signal visible in the image. Keep it under 80 words."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Describe this extracted figure{page_context} from the document '{source_name}'. "
                        "Focus on what a retrieval system should know about it."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _image_data_url(image_path),
                    },
                },
            ],
        },
    ]
    return call_foundry_text(messages, max_completion_tokens=220)


def stitch_segment_boundary_with_foundry(
    previous_text: str,
    next_text: str,
    *,
    previous_heading: str,
    next_heading: str,
) -> str | None:
    if not settings.azure_foundry_chat_enabled:
        return None

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You decide whether two extracted text fragments from adjacent PDF segments belong to the same paragraph. "
                "Return strict JSON only with keys merge and merged_text. "
                "Set merge to true only if the second fragment is a direct continuation of the first. "
                "If merge is false, set merged_text to an empty string. "
                "If merge is true, preserve the original wording and make only the minimum edits needed to join the fragments cleanly."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Previous heading: {previous_heading}\n"
                f"Next heading: {next_heading}\n"
                f"Previous fragment:\n{previous_text}\n\n"
                f"Next fragment:\n{next_text}\n\n"
                'Return JSON like {"merge": true, "merged_text": "..."}'
            ),
        },
    ]
    answer, _ = call_foundry_text(messages, max_completion_tokens=240)
    normalized = answer.strip()
    fence_match = re.search(r"\{.*\}", normalized, flags=re.DOTALL)
    if fence_match:
        normalized = fence_match.group(0)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if not payload.get("merge"):
        return None
    merged_text = payload.get("merged_text")
    if not isinstance(merged_text, str) or not merged_text.strip():
        return None
    return merged_text.strip()
