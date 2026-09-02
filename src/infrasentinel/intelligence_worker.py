from __future__ import annotations

import argparse
import socket
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import SessionLocal, get_engine, utc_now
from .detection_media import resolve_storage_key
from .detection_models import DetectionMedia, DetectionObservation, MediaRole
from .intelligence_models import (
    AnalysisStatus,
    DetectionEvent,
    LlmAnalysis,
    LlmCall,
)
from .intelligence_service import claim_next_analysis, provider_credential_for_analysis
from .llm_adapter import LlmAdapterError, analyze_image, decrypt_api_key


class IntelligenceWorker:
    def __init__(
        self,
        settings: Settings | None = None,
        worker_id: str | None = None,
        analyzer=analyze_image,
    ) -> None:
        self.settings = settings or get_settings()
        self.worker_id = worker_id or f"{socket.gethostname()}-llm"
        self.analyzer = analyzer

    def _media_and_observations(
        self, db: Session, analysis: LlmAnalysis
    ) -> tuple[DetectionMedia, list[DetectionObservation]]:
        if analysis.job_id:
            media = db.scalar(
                select(DetectionMedia)
                .where(
                    DetectionMedia.job_id == analysis.job_id,
                    DetectionMedia.role == MediaRole.ANNOTATED,
                    DetectionMedia.mime_type.like("image/%"),
                )
                .order_by(DetectionMedia.created_at.desc())
                .limit(1)
            )
            observations = list(
                db.scalars(
                    select(DetectionObservation).where(
                        DetectionObservation.job_id == analysis.job_id
                    )
                )
            )
        else:
            event = db.get(DetectionEvent, analysis.event_id)
            media = db.get(DetectionMedia, event.keyframe_media_id) if event else None
            observations = (
                list(
                    db.scalars(
                        select(DetectionObservation).where(
                            DetectionObservation.job_id == event.job_id,
                            DetectionObservation.class_name == event.class_name,
                            DetectionObservation.timestamp_ms >= event.first_timestamp_ms,
                            DetectionObservation.timestamp_ms <= event.last_timestamp_ms,
                        )
                    )
                )
                if event
                else []
            )
        if media is None or not observations:
            raise LlmAdapterError("llm.media_unavailable")
        return media, observations

    def process(self, db: Session, analysis: LlmAnalysis) -> None:
        started = time.perf_counter()
        configured = provider_credential_for_analysis(db, analysis)
        if configured is None:
            analysis.status = AnalysisStatus.WAITING_CONFIGURATION
            analysis.error_code = "llm.configuration_missing"
            analysis.claimed_by = None
            analysis.lease_expires_at = None
            db.commit()
            return
        provider, credential = configured
        analysis.provider_config_id = provider.id
        request_bytes = response_bytes = 0
        error_code = None
        succeeded = False
        try:
            media, observations = self._media_and_observations(db, analysis)
            path = resolve_storage_key(self.settings.storage_root, media.storage_key)
            image = path.read_bytes()
            result = self.analyzer(
                endpoint=provider.endpoint,
                model=provider.model_name,
                api_key=decrypt_api_key(
                    self.settings.infrasentinel_secret_key.get_secret_value(),
                    credential.encrypted_key,
                ),
                image=image,
                mime_type=media.mime_type,
                observation_ids=[item.id for item in observations],
                timeout_seconds=provider.timeout_seconds,
            )
            request_bytes = result.request_bytes
            response_bytes = result.response_bytes
            analysis.result_json = result.analysis.model_dump(mode="json")
            analysis.status = AnalysisStatus.SUCCEEDED
            analysis.error_code = analysis.error_detail = None
            analysis.finished_at = utc_now()
            succeeded = True
            prompt_tokens = result.prompt_tokens
            completion_tokens = result.completion_tokens
        except Exception as exc:
            if isinstance(exc, LlmAdapterError):
                error_code = exc.code
            elif isinstance(exc, OSError):
                error_code = "llm.media_unavailable"
            else:
                error_code = "llm.processing_failed"
            prompt_tokens = completion_tokens = None
            if analysis.attempt < analysis.max_attempts and error_code not in {
                "llm.media_unavailable",
                "llm.credential_invalid",
            }:
                analysis.attempt += 1
                analysis.status = AnalysisStatus.QUEUED
            else:
                analysis.status = AnalysisStatus.FAILED
                analysis.finished_at = utc_now()
            analysis.error_code = error_code
            analysis.error_detail = None
        finally:
            analysis.claimed_by = None
            analysis.lease_expires_at = None
            db.add(
                LlmCall(
                    analysis_id=analysis.id,
                    provider_config_id=provider.id,
                    succeeded=succeeded,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    request_bytes=request_bytes,
                    response_bytes=response_bytes,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_code=error_code,
                )
            )
            db.commit()

    def run_once(self) -> bool:
        with SessionLocal(bind=get_engine()) as db:
            analysis = claim_next_analysis(
                db, self.worker_id, self.settings.infrasentinel_task_lease_seconds
            )
            if analysis is None:
                return False
            self.process(db, analysis)
            return True

    def run(self) -> None:
        while True:
            if not self.run_once():
                time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(prog="infrasentinel-intelligence-worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    worker = IntelligenceWorker()
    if args.once:
        return 0 if worker.run_once() else 2
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
