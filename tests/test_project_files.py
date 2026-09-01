from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_protected_asset_patterns_are_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("datasets/", "models/", "runs/", "runtime/", "*.pt", "*.engine", ".env"):
        assert pattern in ignore


def test_compose_images_are_pinned() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert ":latest" not in compose
    assert "postgres:17.11-bookworm" in compose
    assert "redis:8.2.9-bookworm" in compose
    assert "milvusdb/milvus:v2.6.21" in compose


def test_dependency_ports_are_bound_to_loopback() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    for port in (5432, 6379, 9000, 9001, 19530, 9091):
        assert f'"127.0.0.1:{port}:{port}"' in compose
