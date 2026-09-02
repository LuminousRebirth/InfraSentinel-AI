import uuid

from infrasentinel.detection_models import DetectionObservation
from infrasentinel.intelligence_service import box_iou, group_observations


def observation(
    *,
    timestamp_ms: int,
    box: tuple[float, float, float, float],
    class_name: str = "CK",
    confidence: float = 0.8,
) -> DetectionObservation:
    return DetectionObservation(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        frame_index=timestamp_ms // 100,
        timestamp_ms=timestamp_ms,
        class_name=class_name,
        confidence=confidence,
        x1=box[0],
        y1=box[1],
        x2=box[2],
        y2=box[3],
        inference_ms=5,
    )


def test_grouping_respects_class_time_iou_and_image_boundaries() -> None:
    first = observation(timestamp_ms=0, box=(0, 0, 10, 10), confidence=0.7)
    overlapping = observation(timestamp_ms=3000, box=(1, 1, 11, 11), confidence=0.9)
    too_late = observation(timestamp_ms=6001, box=(1, 1, 11, 11))
    other_class = observation(timestamp_ms=1000, box=(1, 1, 11, 11), class_name="SG")

    assert box_iou(first, overlapping) > 0.30
    groups = group_observations(
        [too_late, other_class, overlapping, first],
        image=False,
        merge_window_ms=3000,
        iou_threshold=0.30,
    )
    assert [len(group.observations) for group in groups] == [2, 1, 1]
    assert groups[0].representative is overlapping
    assert len(group_observations([first, overlapping], image=True)) == 2
