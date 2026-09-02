from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from redis import Redis
from sqlalchemy.orm import Session

from vision_inspection.infer import SceneRuntime

from .config import Settings, get_settings
from .database import SessionLocal, get_engine, utc_now
from .detection_media import resolve_storage_key
from .detection_models import (
    DetectionJob,
    DetectionKind,
    DetectionMedia,
    DetectionMetric,
    DetectionObservation,
    JobStatus,
    MediaRole,
    MediaType,
    VisionModel,
)
from .detection_service import (
    cancel_running_job,
    cancellation_requested,
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_job,
    input_media_for_job,
)
from .vision_models import sha256_file


def class_counts(detections: list[dict]) -> dict[str, int]:
    return dict(Counter(item["cls"] for item in detections))


def ffmpeg_executable() -> str:
    bundled = Path(sys.executable).parent / "Library" / "bin" / "ffmpeg.exe"
    return str(bundled) if bundled.is_file() else "ffmpeg"


def _observations(
    job: DetectionJob,
    detections: list[dict],
    inference_ms: float,
    *,
    frame_index: int = 0,
    timestamp_ms: int = 0,
) -> list[DetectionObservation]:
    return [
        DetectionObservation(
            job_id=job.id,
            frame_index=frame_index,
            timestamp_ms=timestamp_ms,
            class_name=item["cls"],
            confidence=float(item["conf"]),
            x1=float(item["box"][0]),
            y1=float(item["box"][1]),
            x2=float(item["box"][2]),
            y2=float(item["box"][3]),
            inference_ms=inference_ms,
        )
        for item in detections
    ]


class VisionWorker:
    def __init__(self, settings: Settings | None = None, worker_id: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.runtimes: dict[uuid.UUID, SceneRuntime] = {}

    def runtime_for(self, model: VisionModel) -> SceneRuntime:
        cached = self.runtimes.get(model.id)
        if cached is not None:
            return cached
        if not model.pt_path:
            raise RuntimeError("configured PT model is unavailable")
        engine = Path(model.engine_path) if model.engine_path else None
        try:
            runtime = SceneRuntime(
                model.scene.value if hasattr(model.scene, "value") else str(model.scene),
                Path(model.pt_path),
                engine=engine,
                backend="auto",
            )
        except Exception:
            runtime = SceneRuntime(
                model.scene.value if hasattr(model.scene, "value") else str(model.scene),
                Path(model.pt_path),
                backend="pt",
            )
        self.runtimes[model.id] = runtime
        return runtime

    def process_job(self, db: Session, job: DetectionJob, runtime=None) -> None:
        model = db.get(VisionModel, job.model_id)
        if model is None:
            fail_job(db, job, "detection.model_not_found")
            return
        try:
            runtime = runtime or self.runtime_for(model)
            if job.kind == DetectionKind.IMAGE:
                self.process_image(db, job, runtime)
            elif job.kind == DetectionKind.VIDEO:
                self.process_video(db, job, runtime)
            else:
                self.process_obs(db, job, runtime)
        except Exception as exc:
            db.rollback()
            current = db.get(DetectionJob, job.id)
            if current and current.status not in {JobStatus.CANCELLED, JobStatus.SUCCEEDED}:
                fail_job(db, current, "detection.processing_failed", str(exc))

    def _prediction(self, runtime, image, parameters: dict):
        return runtime.predict(
            image,
            conf=float(parameters.get("confidence", 0.35)),
            iou=float(parameters.get("iou", 0.70)),
            imgsz=parameters.get("input_size"),
            device=str(parameters.get("device", self.settings.infrasentinel_vision_device)),
        )

    def _output_path(
        self, job: DetectionJob, suffix: str, role: str = "annotated"
    ) -> tuple[str, Path]:
        now = utc_now()
        token = uuid.uuid4().hex
        key = f"{role}/{now:%Y/%m}/{job.id}/{token}{suffix}"
        path = resolve_storage_key(self.settings.storage_root, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return key, path

    def _save_keyframe(
        self,
        db: Session,
        job: DetectionJob,
        image,
        *,
        label: str,
    ) -> None:
        storage_key, path = self._output_path(job, ".jpg", role="keyframes")
        temporary = path.with_suffix(".part.jpg")
        if not cv2.imwrite(str(temporary), image):
            raise RuntimeError("keyframe write failed")
        os.replace(temporary, path)
        height, width = image.shape[:2]
        db.add(
            DetectionMedia(
                job_id=job.id,
                role=MediaRole.KEYFRAME,
                media_type=MediaType.IMAGE,
                storage_key=storage_key,
                original_name=f"keyframe-{label}.jpg",
                mime_type="image/jpeg",
                byte_size=path.stat().st_size,
                sha256=sha256_file(path),
                width=width,
                height=height,
            )
        )

    def process_image(self, db: Session, job: DetectionJob, runtime) -> None:
        source = input_media_for_job(db, job)
        if source is None:
            raise RuntimeError("original media is missing")
        source_path = resolve_storage_key(self.settings.storage_root, source.storage_key)
        image = cv2.imread(str(source_path))
        if image is None:
            raise RuntimeError("image decode failed")
        if cancellation_requested(db, job.id):
            cancel_running_job(db, job)
            return
        prediction = self._prediction(runtime, image, job.parameters_json)
        storage_key, output_path = self._output_path(job, ".jpg")
        temporary = output_path.with_suffix(".part.jpg")
        if not cv2.imwrite(str(temporary), prediction.annotated_image):
            raise RuntimeError("annotated image write failed")
        os.replace(temporary, output_path)
        height, width = prediction.annotated_image.shape[:2]
        db.add(
            DetectionMedia(
                job_id=job.id,
                role=MediaRole.ANNOTATED,
                media_type=MediaType.IMAGE,
                storage_key=storage_key,
                original_name=f"annotated-{source.original_name.rsplit('.', 1)[0]}.jpg",
                mime_type="image/jpeg",
                byte_size=output_path.stat().st_size,
                sha256=sha256_file(output_path),
                width=width,
                height=height,
            )
        )
        db.add_all(_observations(job, prediction.detections, prediction.inference_ms))
        db.add(
            DetectionMetric(
                job_id=job.id,
                sample_at=utc_now(),
                processed_frames=1,
                effective_fps=round(1000 / max(prediction.inference_ms, 0.01), 3),
                inference_p50_ms=prediction.inference_ms,
            )
        )
        complete_job(
            db,
            job,
            {
                "class_counts": class_counts(prediction.detections),
                "detections": len(prediction.detections),
                "inference_ms": prediction.inference_ms,
                "backend": prediction.backend,
            },
        )

    def process_video(self, db: Session, job: DetectionJob, runtime) -> None:
        source = input_media_for_job(db, job)
        if source is None:
            raise RuntimeError("original media is missing")
        source_path = resolve_storage_key(self.settings.storage_root, source.storage_key)
        capture = cv2.VideoCapture(str(source_path))
        if not capture.isOpened():
            raise RuntimeError("video decode failed")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        target_fps = min(fps, float(job.parameters_json.get("detection_fps") or 10))
        frame_step = max(1, round(fps / target_fps))
        storage_key, output_path = self._output_path(job, ".mp4")
        raw_path = output_path.with_suffix(".part.avi")
        writer = cv2.VideoWriter(
            str(raw_path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height)
        )
        if not writer.isOpened():
            capture.release()
            raise RuntimeError("video output could not be opened")
        all_detections: list[dict] = []
        inference_times: list[float] = []
        next_keyframe_ms = 0
        keyframe_count = 0
        processed = frame_index = 0
        started = time.perf_counter()
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                output = frame
                if frame_index % frame_step == 0:
                    if cancellation_requested(db, job.id):
                        cancel_running_job(db, job)
                        raw_path.unlink(missing_ok=True)
                        return
                    prediction = self._prediction(runtime, frame, job.parameters_json)
                    output = prediction.annotated_image
                    timestamp_ms = round(frame_index / fps * 1000)
                    db.add_all(
                        _observations(
                            job,
                            prediction.detections,
                            prediction.inference_ms,
                            frame_index=frame_index,
                            timestamp_ms=timestamp_ms,
                        )
                    )
                    all_detections.extend(prediction.detections)
                    inference_times.append(prediction.inference_ms)
                    processed += 1
                    if (
                        prediction.detections
                        and timestamp_ms >= next_keyframe_ms
                        and keyframe_count < 100
                    ):
                        self._save_keyframe(
                            db,
                            job,
                            prediction.annotated_image,
                            label=f"{timestamp_ms:010d}",
                        )
                        next_keyframe_ms = timestamp_ms + 5000
                        keyframe_count += 1
                    if processed % 10 == 0:
                        heartbeat_job(
                            db,
                            job.id,
                            self.worker_id,
                            self.settings.infrasentinel_task_lease_seconds,
                            progress=round(frame_index / max(frame_count, 1) * 100),
                            detail="processing video",
                        )
                writer.write(output)
                frame_index += 1
        finally:
            capture.release()
            writer.release()
        if frame_index == 0:
            raw_path.unlink(missing_ok=True)
            raise RuntimeError("video contained no frames")
        try:
            subprocess.run(
                [
                    ffmpeg_executable(),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(raw_path),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(output_path),
                ],
                check=True,
                timeout=max(120, round(frame_index / fps * 4)),
            )
        except Exception:
            output_path.unlink(missing_ok=True)
            raise
        finally:
            raw_path.unlink(missing_ok=True)
        elapsed = max(time.perf_counter() - started, 0.001)
        median = float(np.median(inference_times)) if inference_times else 0.0
        db.add(
            DetectionMedia(
                job_id=job.id,
                role=MediaRole.ANNOTATED,
                media_type=MediaType.VIDEO,
                storage_key=storage_key,
                original_name=f"annotated-{Path(source.original_name).stem}.mp4",
                mime_type="video/mp4",
                byte_size=output_path.stat().st_size,
                sha256=sha256_file(output_path),
                width=width,
                height=height,
                duration_seconds=round(frame_index / fps, 3),
                fps=fps,
                frame_count=frame_index,
            )
        )
        db.add(
            DetectionMetric(
                job_id=job.id,
                sample_at=utc_now(),
                processed_frames=processed,
                effective_fps=round(frame_index / elapsed, 3),
                inference_p50_ms=round(median, 3),
            )
        )
        complete_job(
            db,
            job,
            {
                "class_counts": class_counts(all_detections),
                "detections": len(all_detections),
                "processed_frames": processed,
                "source_frames": frame_index,
                "effective_fps": round(frame_index / elapsed, 3),
                "inference_p50_ms": round(median, 3),
                "backend": runtime.backend,
                "audio_retained": False,
            },
        )

    def process_obs(
        self, db: Session, job: DetectionJob, runtime, *, capture=None, redis=None
    ) -> None:
        # ponytail: one configured camera index; add a source registry only with multi-camera scope.
        capture = capture or cv2.VideoCapture(
            self.settings.infrasentinel_obs_camera_index, cv2.CAP_DSHOW
        )
        if not capture.isOpened():
            raise RuntimeError("OBS virtual camera is unavailable")
        redis = redis or Redis.from_url(self.settings.redis_url.get_secret_value())
        frame_index = processed = 0
        inference_times: list[float] = []
        next_keyframe_ms = 0
        keyframe_count = 0
        current_resolution = ""
        started = last_detection = time.perf_counter()
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError("OBS frame capture failed")
                db.expire(job, ["status", "parameters_json"])
                if cancellation_requested(db, job.id):
                    cancel_running_job(db, job)
                    return
                resolution = str(job.parameters_json.get("resolution") or "720p")
                if resolution != current_resolution:
                    width, height = (1280, 720) if resolution == "720p" else (960, 640)
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    current_resolution = resolution
                target_fps = float(job.parameters_json.get("detection_fps") or 15)
                now = time.perf_counter()
                if now - last_detection < 1 / target_fps:
                    frame_index += 1
                    continue
                prediction = self._prediction(runtime, frame, job.parameters_json)
                last_detection = now
                timestamp_ms = round((now - started) * 1000)
                db.add_all(
                    _observations(
                        job,
                        prediction.detections,
                        prediction.inference_ms,
                        frame_index=frame_index,
                        timestamp_ms=timestamp_ms,
                    )
                )
                inference_times.append(prediction.inference_ms)
                processed += 1
                if (
                    prediction.detections
                    and timestamp_ms >= next_keyframe_ms
                    and keyframe_count < 500
                ):
                    self._save_keyframe(
                        db,
                        job,
                        prediction.annotated_image,
                        label=f"live-{timestamp_ms:010d}",
                    )
                    next_keyframe_ms = timestamp_ms + 10000
                    keyframe_count += 1
                ok, encoded = cv2.imencode(".jpg", prediction.annotated_image)
                if ok:
                    redis.setex(f"infrasentinel:obs:{job.id}:preview", 3, encoded.tobytes())
                if processed % 15 == 0:
                    elapsed = max(time.perf_counter() - started, 0.001)
                    db.add(
                        DetectionMetric(
                            job_id=job.id,
                            sample_at=utc_now(),
                            processed_frames=processed,
                            effective_fps=round(processed / elapsed, 3),
                            inference_p50_ms=round(float(np.median(inference_times[-60:])), 3),
                        )
                    )
                    heartbeat_job(
                        db,
                        job.id,
                        self.worker_id,
                        self.settings.infrasentinel_task_lease_seconds,
                        progress=0,
                        detail="live",
                    )
                frame_index += 1
        finally:
            capture.release()
            redis.delete(f"infrasentinel:obs:{job.id}:preview")
            redis.close()

    def run_once(self) -> bool:
        with SessionLocal(bind=get_engine()) as db:
            job = claim_next_job(db, self.worker_id, self.settings.infrasentinel_task_lease_seconds)
            if job is None:
                return False
            self.process_job(db, job)
            return True

    def run(self) -> None:
        while True:
            if not self.run_once():
                time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(prog="infrasentinel-worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    worker = VisionWorker()
    if args.once:
        return 0 if worker.run_once() else 2
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
