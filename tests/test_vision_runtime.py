from pathlib import Path

import cv2
import numpy as np

from infrasentinel.vision_models import inspect_asset, sha256_file
from vision_inspection.infer import annotate_detections


def test_model_asset_inspection_and_hash_are_safe(tmp_path: Path) -> None:
    model = tmp_path / "model.pt"
    model.write_bytes(b"model-bytes")
    resolved, error = inspect_asset(model, ".pt")
    assert resolved == str(model.resolve())
    assert error is None
    assert sha256_file(model) == "357e5d6fafa34d27360fec24b4326d3534905e33c6acdee60198fb078b7b79e5"


def test_model_asset_inspection_hides_missing_path() -> None:
    resolved, error = inspect_asset(Path("private/missing.pt"), ".pt")
    assert resolved is None
    assert error == "configured model asset is unavailable"
    assert "private" not in error


def test_annotation_clamps_boxes_and_changes_a_copy() -> None:
    image = np.zeros((40, 60, 3), dtype=np.uint8)
    annotated = annotate_detections(
        image,
        [{"cls": "CK", "conf": 0.9, "box": [-5, -2, 100, 80]}],
    )
    assert np.count_nonzero(image) == 0
    assert np.count_nonzero(annotated) > 0
    assert annotated.shape == image.shape
    assert cv2.imencode(".jpg", annotated)[0]
