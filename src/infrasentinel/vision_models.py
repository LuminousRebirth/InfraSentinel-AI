from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .database import utc_now
from .detection_models import ModelAvailability, ModelBackend, VisionModel, VisionScene


@dataclass(frozen=True)
class ModelSpec:
    code: str
    scene: VisionScene
    name_zh: str
    name_en: str
    classes: tuple[str, ...]
    input_size: int
    pt_setting: str
    engine_setting: str


MODEL_SPECS = (
    ModelSpec(
        code="pipeline-local",
        scene=VisionScene.PIPELINE,
        name_zh="管道缺陷模型",
        name_en="Pipeline defect model",
        classes=("CK", "PL", "SG", "SL", "TL", "ZW"),
        input_size=640,
        pt_setting="infrasentinel_pipeline_pt",
        engine_setting="infrasentinel_pipeline_engine",
    ),
    ModelSpec(
        code="ppe-local",
        scene=VisionScene.PPE,
        name_zh="安全帽识别模型",
        name_en="Helmet safety model",
        classes=("no_helmet", "helmet"),
        input_size=960,
        pt_setting="infrasentinel_ppe_pt",
        engine_setting="infrasentinel_ppe_engine",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_asset(path: Path | None, suffix: str) -> tuple[str | None, str | None]:
    if path is None:
        return None, "model asset is not configured"
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return None, "configured model asset is unavailable"
    if resolved.suffix.lower() != suffix:
        return None, f"model asset must use {suffix}"
    return str(resolved), None


def sync_vision_models(db: Session, settings: Settings) -> list[VisionModel]:
    synced: list[VisionModel] = []
    for spec in MODEL_SPECS:
        pt_path, pt_error = inspect_asset(getattr(settings, spec.pt_setting), ".pt")
        engine_path, _ = inspect_asset(getattr(settings, spec.engine_setting), ".engine")
        asset_hash = sha256_file(Path(pt_path)) if pt_path else None
        model = db.scalar(select(VisionModel).where(VisionModel.code == spec.code))
        if model is None:
            model = VisionModel(code=spec.code)
            db.add(model)
        model.name_zh = spec.name_zh
        model.name_en = spec.name_en
        model.scene = spec.scene
        model.pt_path = pt_path
        model.engine_path = engine_path
        model.asset_sha256 = asset_hash
        model.classes_json = list(spec.classes)
        model.input_size = spec.input_size
        model.preferred_backend = ModelBackend.AUTO
        model.availability = (
            ModelAvailability.AVAILABLE if pt_path else ModelAvailability.UNAVAILABLE
        )
        model.unavailable_reason = pt_error
        model.version_label = asset_hash[:12] if asset_hash else "unavailable"
        model.synced_at = utc_now()
        synced.append(model)
    db.commit()
    for model in synced:
        db.refresh(model)
    return synced
