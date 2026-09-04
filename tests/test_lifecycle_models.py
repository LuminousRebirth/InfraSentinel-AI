from sqlalchemy import CheckConstraint

from infrasentinel.database import Base
from infrasentinel.lifecycle_models import (
    LifecycleJobKind,
    LifecycleJobStatus,
    SampleSplit,
    VersionStatus,
)


def test_lifecycle_tables_and_states_are_registered() -> None:
    expected = {
        "dataset_categories",
        "datasets",
        "dataset_versions",
        "dataset_samples",
        "sample_annotations",
        "dataset_changes",
        "quality_findings",
        "lifecycle_jobs",
        "training_metrics",
        "lifecycle_artifacts",
        "managed_model_versions",
        "model_deployments",
    }
    assert expected <= set(Base.metadata.tables)
    assert {item.value for item in SampleSplit} == {"unassigned", "train", "val", "test"}
    assert VersionStatus.FROZEN.value == "frozen"
    assert LifecycleJobKind.TRAIN.value == "train"
    assert LifecycleJobStatus.CANCELLING.value == "cancelling"


def test_lifecycle_critical_database_constraints_are_registered() -> None:
    expected = {
        "dataset_versions": {
            "ck_dataset_split_ranges",
            "ck_dataset_split_sum",
            "ck_dataset_version_counters",
        },
        "dataset_samples": {
            "ck_dataset_sample_dimensions",
            "ck_dataset_sample_review_status",
            "ck_dataset_sample_split",
        },
        "sample_annotations": {"ck_annotation_within_image"},
        "lifecycle_jobs": {"ck_lifecycle_job_kind", "ck_lifecycle_job_status"},
        "training_metrics": {"ck_training_metric_scores"},
    }
    for table_name, constraint_names in expected.items():
        actual = {
            constraint.name
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert constraint_names <= actual
