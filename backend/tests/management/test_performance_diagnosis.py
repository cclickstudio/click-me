"""성과 미달 진단 축 + 진단 LLM ReAct 폴백 — 결정론 경로·통합 경로 검증.

게이트 #9(키 없이 재현) 기준: LLM 키 없이도 전 경로가 결정론으로 동작해야 한다.
"""

from datetime import UTC, datetime

from api.routers.management import _campaign_diagnosis
from domain.management.adapters.mock import MockAdPlatform
from domain.management.agents.diagnosis_llm import run_llm_diagnosis
from domain.management.contracts.enums import (
    AnomalyType,
    DiagnosisSource,
    DiagnosisStatus,
    RelevanceRank,
)
from domain.management.contracts.schemas import (
    DeliveryStatusDetail,
    DiagnosisResult,
    RelevanceDiagnostics,
)
from domain.management.detection.performance_dx import diagnose_performance

NOW = datetime(2026, 6, 21, tzinfo=UTC)


def _relevance(conv: RelevanceRank) -> RelevanceDiagnostics:
    return RelevanceDiagnostics(campaign_id="c1", conversion_rate_ranking=conv, as_of=NOW)


# ── 결정론 성과 미달 진단 ──────────────────────────────────────────


def test_below_target_with_below_average_rank_is_confirmed():
    dx = diagnose_performance(
        "org",
        "c1",
        roas=1.0,
        target_roas=3.0,
        as_of=NOW,
        relevance=_relevance(RelevanceRank.BELOW_AVERAGE_20),
    )
    assert dx is not None
    assert dx.anomaly_type is AnomalyType.PERFORMANCE_BELOW_TARGET
    assert dx.status is DiagnosisStatus.CONFIRMED
    assert dx.source is DiagnosisSource.DETERMINISTIC
    assert dx.evidence_metrics["conversion_rate_ranking"] == "below_average_20"


def test_below_target_with_average_rank_is_inconclusive():
    dx = diagnose_performance(
        "org",
        "c1",
        roas=1.5,
        target_roas=3.0,
        as_of=NOW,
        relevance=_relevance(RelevanceRank.AVERAGE),
    )
    assert dx is not None
    assert dx.status is DiagnosisStatus.INCONCLUSIVE


def test_within_tolerance_returns_none():
    # 2.5 ≥ 3.0×0.7=2.1 → 정상, 진단 없음(오탐 금지).
    dx = diagnose_performance(
        "org",
        "c1",
        roas=2.5,
        target_roas=3.0,
        as_of=NOW,
        relevance=_relevance(RelevanceRank.AVERAGE),
    )
    assert dx is None


def test_missing_roas_or_target_returns_none():
    assert diagnose_performance("org", "c1", roas=None, target_roas=3.0, as_of=NOW) is None
    assert diagnose_performance("org", "c1", roas=1.0, target_roas=None, as_of=NOW) is None


# ── Mock reader 신규 신호(Port 충족) ───────────────────────────────


async def test_mock_reader_exposes_new_signals():
    reader = MockAdPlatform()
    rel = await reader.get_relevance_diagnostics("c1")
    status = await reader.get_delivery_status_detail("c1")
    assert isinstance(rel, RelevanceDiagnostics)
    assert isinstance(status, DeliveryStatusDetail)
    assert status.effective_status == "ACTIVE"  # 데모 정상 게재


# ── LLM ReAct 폴백 (키 없으면 prior 그대로 — 게이트 #9) ─────────────


async def test_llm_diagnosis_falls_back_without_key():
    prior = DiagnosisResult(
        diagnosis_id="d1",
        tenant_id="org",
        campaign_id="c1",
        anomaly_type=AnomalyType.PERFORMANCE_BELOW_TARGET,
        source=DiagnosisSource.DETERMINISTIC,
        hypothesis="목표 미달",
        confidence=0.5,
        metrics_as_of=NOW,
        status=DiagnosisStatus.INCONCLUSIVE,
    )
    result = await run_llm_diagnosis(
        prior, MockAdPlatform(), model="gpt-4o-mini", temperature=0.0, api_key=None
    )
    assert result is prior  # 키 없음 → 결정론 폴백(LLM 미호출)


# ── 통합 경로 (Mock·키 없이 — /campaigns/{id} 상세가 쓰는 헬퍼) ──────


async def test_campaign_diagnosis_integration_below_target():
    summary = {"roas": 1.0, "target_roas": 3.0}
    out = await _campaign_diagnosis(MockAdPlatform(), "c1", summary, NOW)
    assert out is not None
    assert out["anomaly_type"] == "performance_below_target"
    assert out["source"] == "deterministic"  # use_mock=True → LLM 폴백(결정론 유지)
    assert "hypothesis" in out


async def test_campaign_diagnosis_none_when_on_target():
    summary = {"roas": 3.5, "target_roas": 3.0}  # 목표 초과 → 진단 없음
    out = await _campaign_diagnosis(MockAdPlatform(), "c1", summary, NOW)
    assert out is None
