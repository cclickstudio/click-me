"""공유 진단 함수 diagnose_campaign — 도메인 진입점 직접 검증(규칙·None·예외 안전).

라우터 _campaign_diagnosis가 위임하는 정본. use_mock=True(기본)면 LLM 폴백=결정론(게이트 #9).
"""

from datetime import UTC, datetime

from core.config import settings
from domain.management.adapters.mock import MockAdPlatform
from domain.management.detection.agentic_scan import diagnose_campaign

NOW = datetime(2026, 6, 21, tzinfo=UTC)


async def test_diagnose_campaign_below_target_returns_dict():
    out = await diagnose_campaign(
        MockAdPlatform(), settings, "c1", {"roas": 1.0, "target_roas": 3.0}, NOW
    )
    assert out is not None
    assert out["anomaly_type"] == "performance_below_target"
    assert out["source"] == "deterministic"  # use_mock → LLM 폴백(결정론)
    assert "hypothesis" in out


async def test_diagnose_campaign_none_when_on_target():
    out = await diagnose_campaign(
        MockAdPlatform(), settings, "c1", {"roas": 3.5, "target_roas": 3.0}, NOW
    )
    assert out is None


async def test_diagnose_campaign_swallows_reader_error():
    class _BoomReader:
        async def get_relevance_diagnostics(self, campaign_id: str):
            raise RuntimeError("meta down")

    # 신호 조회 실패해도 예외를 삼키고 None(호출부 화면·스캔을 막지 않음).
    out = await diagnose_campaign(
        _BoomReader(), settings, "c1", {"roas": 1.0, "target_roas": 3.0}, NOW
    )
    assert out is None
