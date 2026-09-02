from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.config import Settings
from infrasentinel.database import Base
from infrasentinel.detection_models import (
    DetectionJob,
    DetectionKind,
    DetectionMedia,
    DetectionObservation,
    JobStatus,
    MediaRole,
    MediaType,
    ModelAvailability,
    VisionModel,
    VisionScene,
)
from infrasentinel.intelligence_models import (
    AnalysisStatus,
    LlmAnalysis,
    LlmCall,
    LlmCredential,
    LlmProvider,
    LlmProviderConfig,
)
from infrasentinel.intelligence_schemas import AnalysisResult
from infrasentinel.intelligence_worker import IntelligenceWorker
from infrasentinel.llm_adapter import AdapterResult, encrypt_api_key
from infrasentinel.models import Project, User, UserRole, UserStatus


def test_worker_persists_bounded_success(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    settings = Settings(storage_root=tmp_path, infrasentinel_secret_key="worker-test-secret")
    with Session(engine) as db:
        user = User(
            email="worker@example.com",
            username="worker",
            display_name="Worker",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ENABLED,
        )
        project = Project(code="WORKER", name="Worker project")
        model = VisionModel(
            code="worker-model",
            name_zh="模型",
            name_en="Model",
            scene=VisionScene.PIPELINE,
            classes_json=["CK"],
            input_size=640,
            availability=ModelAvailability.AVAILABLE,
        )
        db.add_all([user, project, model])
        db.flush()
        job = DetectionJob(
            kind=DetectionKind.IMAGE,
            status=JobStatus.SUCCEEDED,
            project_id=project.id,
            point_id=project.id,
            owner_id=user.id,
            model_id=model.id,
            scene=model.scene,
            parameters_json={},
        )
        db.add(job)
        db.flush()
        observation = DetectionObservation(
            job_id=job.id,
            frame_index=0,
            timestamp_ms=0,
            class_name="CK",
            confidence=0.8,
            x1=0,
            y1=0,
            x2=10,
            y2=10,
            inference_ms=5,
        )
        db.add(observation)
        image_path = tmp_path / "annotated.jpg"
        image_path.write_bytes(b"image")
        db.add(
            DetectionMedia(
                job_id=job.id,
                role=MediaRole.ANNOTATED,
                media_type=MediaType.IMAGE,
                storage_key="annotated.jpg",
                original_name="annotated.jpg",
                mime_type="image/jpeg",
                byte_size=5,
                sha256="0" * 64,
                width=1,
                height=1,
            )
        )
        provider = LlmProviderConfig(
            code="local",
            provider=LlmProvider.QWEN,
            endpoint="http://127.0.0.1:9009/v1",
            model_name="vision",
            created_by=user.id,
        )
        db.add(provider)
        db.flush()
        db.add(
            LlmCredential(
                provider_config_id=provider.id,
                scope_key="system",
                encrypted_key=encrypt_api_key("worker-test-secret", "provider-secret"),
                key_hint="…cret",
            )
        )
        analysis = LlmAnalysis(
            job_id=job.id,
            owner_id=user.id,
            provider_config_id=provider.id,
            status=AnalysisStatus.RUNNING,
            prefer_personal=True,
        )
        db.add(analysis)
        db.commit()

        def analyzer(**kwargs):
            assert kwargs["api_key"] == "provider-secret"
            assert kwargs["observation_ids"] == [observation.id]
            return AdapterResult(
                analysis=AnalysisResult(
                    objects=[],
                    global_risk="medium",
                    conclusion="Inspect",
                    priorities=[],
                    associations=[],
                ),
                request_bytes=10,
                response_bytes=20,
                prompt_tokens=1,
                completion_tokens=2,
            )

        IntelligenceWorker(settings=settings, worker_id="test", analyzer=analyzer).process(
            db, analysis
        )
        assert analysis.status == AnalysisStatus.SUCCEEDED
        assert analysis.result_json["conclusion"] == "Inspect"
        assert db.scalar(select(LlmCall)).succeeded is True
