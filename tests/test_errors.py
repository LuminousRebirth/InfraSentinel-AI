from fastapi.testclient import TestClient

from infrasentinel.errors import MESSAGES, redact_secrets, resolve_locale
from infrasentinel.main import app


def test_locale_keys_and_redaction() -> None:
    assert MESSAGES["zh-CN"].keys() == MESSAGES["en"].keys()
    assert resolve_locale("en-US,en;q=0.9") == "en"
    assert redact_secrets({"nested": {"access_token": "value"}}) == {
        "nested": {"access_token": "[REDACTED]"}
    }


def test_missing_api_uses_safe_bilingual_envelope() -> None:
    response = TestClient(app).get("/api/v1/missing", headers={"Accept-Language": "en"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http.not_found"
    assert response.headers["X-Request-ID"]
