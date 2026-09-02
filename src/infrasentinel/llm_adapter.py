from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError

from .intelligence_schemas import AnalysisResult

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class LlmAdapterError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AdapterResult:
    analysis: AnalysisResult
    request_bytes: int
    response_bytes: int
    prompt_tokens: int | None
    completion_tokens: int | None


def credential_cipher(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_api_key(secret: str, api_key: str) -> bytes:
    value = api_key.strip()
    if not 8 <= len(value) <= 4096:
        raise ValueError("API key must contain 8-4096 characters")
    return credential_cipher(secret).encrypt(value.encode())


def decrypt_api_key(secret: str, encrypted: bytes) -> str:
    try:
        return credential_cipher(secret).decrypt(encrypted).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise LlmAdapterError("llm.credential_invalid") from exc


def validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("provider endpoint must use HTTPS")
    if not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("provider endpoint is invalid")
    return endpoint.rstrip("/")


def _response_body(response: httpx.Response) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise LlmAdapterError("llm.response_too_large")
    return bytes(body)


def analyze_image(
    *,
    endpoint: str,
    model: str,
    api_key: str,
    image: bytes,
    mime_type: str,
    observation_ids: list[uuid.UUID],
    timeout_seconds: int,
    client: httpx.Client | None = None,
) -> AdapterResult:
    if not image or len(image) > MAX_IMAGE_BYTES:
        raise LlmAdapterError("llm.image_size_invalid")
    allowed_ids = {str(item) for item in observation_ids}
    prompt = (
        "Analyze the visual detections. Return JSON only with objects, global_risk, "
        "conclusion, priorities, and associations. Object observation_id must be one of: "
        + ", ".join(sorted(allowed_ids))
    )
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are an industrial safety analysis assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64.b64encode(image).decode()}"
                        },
                    },
                ],
            },
        ],
    }
    request_bytes = len(json.dumps(payload, separators=(",", ":")).encode())
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
    try:
        try:
            with http.stream(
                "POST",
                f"{validate_endpoint(endpoint)}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                follow_redirects=False,
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise LlmAdapterError(f"llm.http_{response.status_code}")
                body = _response_body(response)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise LlmAdapterError("llm.network_failed") from exc
        try:
            envelope = json.loads(body)
            content = envelope["choices"][0]["message"]["content"]
            raw_result = json.loads(content) if isinstance(content, str) else content
            result = AnalysisResult.model_validate(raw_result)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise LlmAdapterError("llm.invalid_response") from exc
        returned_ids = {str(item.observation_id) for item in result.objects}
        if not returned_ids <= allowed_ids:
            raise LlmAdapterError("llm.unknown_observation")
        usage = envelope.get("usage") or {}
        return AdapterResult(
            analysis=result,
            request_bytes=request_bytes,
            response_bytes=len(body),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
    finally:
        if owns_client:
            http.close()
