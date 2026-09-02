import json
import uuid

import httpx
import pytest

from infrasentinel.llm_adapter import (
    LlmAdapterError,
    analyze_image,
    decrypt_api_key,
    encrypt_api_key,
    validate_endpoint,
)


def test_credentials_encrypt_and_endpoint_is_bounded() -> None:
    encrypted = encrypt_api_key("application-secret", "provider-secret-key")
    assert b"provider-secret-key" not in encrypted
    assert decrypt_api_key("application-secret", encrypted) == "provider-secret-key"
    assert validate_endpoint("https://example.com/v1") == "https://example.com/v1"
    assert validate_endpoint("http://127.0.0.1:9009/v1") == "http://127.0.0.1:9009/v1"
    with pytest.raises(ValueError, match="HTTPS"):
        validate_endpoint("http://example.com/v1")


def test_adapter_validates_structured_result_and_observation_ids() -> None:
    observation_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer provider-secret-key"
        content = {
            "objects": [
                {
                    "observation_id": str(observation_id),
                    "severity": "medium",
                    "explanation": "Visible defect",
                    "possible_causes": ["wear"],
                    "repair_suggestions": ["inspect"],
                }
            ],
            "global_risk": "medium",
            "conclusion": "Inspection required",
            "priorities": ["inspect"],
            "associations": [],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = analyze_image(
            endpoint="http://127.0.0.1:9009/v1",
            model="vision-model",
            api_key="provider-secret-key",
            image=b"small-image",
            mime_type="image/jpeg",
            observation_ids=[observation_id],
            timeout_seconds=10,
            client=client,
        )
    assert result.analysis.objects[0].observation_id == observation_id
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20
    assert result.request_bytes > len(b"small-image")


def test_adapter_rejects_invalid_provider_output() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(LlmAdapterError, match="llm.invalid_response"),
    ):
        analyze_image(
            endpoint="http://localhost:9009/v1",
            model="vision-model",
            api_key="provider-secret-key",
            image=b"small-image",
            mime_type="image/jpeg",
            observation_ids=[uuid.uuid4()],
            timeout_seconds=10,
            client=client,
        )
