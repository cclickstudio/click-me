# 🅱 재생성 테스트 공용 픽스처 — rank/package(HITL) API 기준
from datetime import UTC, datetime

import pytest

from domain.management.agents.regeneration import (
    RemediationAgent,
    RemediationContext,
    RiskAppetite,
)
from domain.management.agents.selection import InMemorySelectionRoundStore
from domain.management.contracts.enums import AnomalyType, DiagnosisSource, DiagnosisStatus
from domain.management.contracts.schemas import DiagnosisResult


@pytest.fixture
def make_diagnosis():
    def _make(anomaly=AnomalyType.QUALITY_DEGRADED, confidence=1.0):
        return DiagnosisResult(
            diagnosis_id="dx",
            tenant_id="org_1",
            campaign_id="camp_1",
            anomaly_type=anomaly,
            source=DiagnosisSource.AGENT,
            confidence=confidence,
            evidence_metrics={"existing_ad_s3_key": "old_key"},
            metrics_as_of=datetime.now(UTC),
            status=DiagnosisStatus.CONFIRMED,
        )

    return _make


@pytest.fixture
def make_context():
    def _make(action_type="REPLACE_CREATIVE"):
        return RemediationContext(
            ad_account_id="act_1",
            target_object_ids=("camp_1",),
            budget_before_krw=100_000,
            budget_after_krw=100_000,
            run_days=7,
            expected_state_version="state_v1",
            approval_policy_version="v1",
            risk_appetite=RiskAppetite.CONSERVATIVE,
            action_type=action_type,
        )

    return _make


@pytest.fixture
def make_agent():
    def _make(generator):
        return RemediationAgent(generator=generator, selection_store=InMemorySelectionRoundStore())

    return _make
