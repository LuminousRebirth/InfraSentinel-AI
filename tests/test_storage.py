from __future__ import annotations

from pathlib import Path

import pytest

from infrasentinel.storage import ensure_storage, safe_path


def test_safe_path_accepts_descendant(tmp_path: Path) -> None:
    assert safe_path(tmp_path, "images", "a.jpg") == tmp_path / "images" / "a.jpg"


def test_safe_path_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        safe_path(tmp_path, "..", "secret.txt")


def test_ensure_storage_creates_root(tmp_path: Path) -> None:
    root = tmp_path / "media"
    status = ensure_storage(root, warning_gb=1)
    assert root.is_dir()
    assert status.total_gb > 0
