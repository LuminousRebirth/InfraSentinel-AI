from __future__ import annotations

from pathlib import Path

from infrasentinel.health import _result, _running_worker_count, _storage_result
from infrasentinel.storage import StorageStatus


def test_result_masks_dependency_exception_details() -> None:
    def fail() -> None:
        raise RuntimeError("password=must-not-leak")

    result = _result(fail)
    assert result.status == "unavailable"
    assert result.detail == "RuntimeError"
    assert "must-not-leak" not in result.model_dump_json()


def test_result_reports_success() -> None:
    result = _result(lambda: None)
    assert result.status == "ok"
    assert result.detail is None


def test_storage_warning_is_visible_without_marking_dependency_unavailable() -> None:
    result = _storage_result(
        StorageStatus(root=Path("runtime"), free_gb=12.5, total_gb=100.0, warning=True),
        warning_gb=20,
    )
    assert result.status == "warning"
    assert result.detail == "12.5 GB free; warning threshold is 20 GB"


def test_worker_health_ignores_invalid_and_stale_pid_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "worker-1.pid").write_text("123", encoding="ascii")
    (tmp_path / "worker-2.pid").write_text("not-a-pid", encoding="ascii")
    (tmp_path / "worker-3.pid").write_text("456", encoding="ascii")

    monkeypatch.setattr("infrasentinel.health._pid_is_running", lambda pid: pid == 123)
    assert _running_worker_count(tmp_path) == 1
