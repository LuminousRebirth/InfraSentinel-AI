from __future__ import annotations

import pytest
from sqlalchemy import inspect

from infrasentinel.database import get_engine


@pytest.mark.integration
def test_detection_schema_exists() -> None:
    assert {
        "vision_models",
        "detection_jobs",
        "detection_media",
        "detection_observations",
        "detection_metrics",
    } <= set(inspect(get_engine()).get_table_names())
