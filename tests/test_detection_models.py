from infrasentinel.database import Base
from infrasentinel.detection_models import DetectionKind, JobStatus, VisionScene


def test_detection_metadata_contains_v12_tables() -> None:
    assert {
        "vision_models",
        "detection_jobs",
        "detection_media",
        "detection_observations",
        "detection_metrics",
    } <= set(Base.metadata.tables)
    assert DetectionKind.OBS.value == "obs"
    assert JobStatus.CANCELLING.value == "cancelling"
    assert VisionScene.PIPELINE.value == "pipeline"
