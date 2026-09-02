from infrasentinel.database import Base
from infrasentinel.intelligence_models import AlertStatus, AnalysisStatus, RiskLevel


def test_intelligence_tables_and_states_are_registered() -> None:
    expected = {
        "alert_rules",
        "detection_events",
        "alerts",
        "alert_actions",
        "alert_attachments",
        "llm_provider_configs",
        "llm_credentials",
        "llm_analyses",
        "llm_calls",
    }
    assert expected <= set(Base.metadata.tables)
    assert {item.value for item in RiskLevel} == {"low", "medium", "high"}
    assert AlertStatus.PENDING_CONFIRMATION.value == "pending_confirmation"
    assert AnalysisStatus.WAITING_CONFIGURATION.value == "waiting_configuration"
