from pathlib import Path


def test_v14_migration_is_reversible_and_constrained() -> None:
    migration = Path("alembic/versions/20260903_0005_lifecycle.py").read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260902_0004"' in migration
    assert "def downgrade()" in migration
    for table in (
        "dataset_categories",
        "datasets",
        "dataset_versions",
        "dataset_samples",
        "sample_annotations",
        "lifecycle_jobs",
        "managed_model_versions",
        "model_deployments",
    ):
        assert f'"{table}"' in migration
    assert "ck_dataset_split_ranges" in migration
    assert "ck_annotation_within_image" in migration
    assert "ck_lifecycle_job_status" in migration
    assert "ck_managed_model_scene" in migration
