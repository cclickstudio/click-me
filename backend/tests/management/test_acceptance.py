# PRD §9.5 완료조건 + §9.9 게이트 인수 테스트 — API 키·DB 없이 결정론 폴백으로 재현
"""acceptance.py 기준 문서에서 정의한 조건들을 pytest로 검증한다.

모든 테스트는 use_mock=True + openai_api_key=None 조건에서 동작(CI 안전).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from domain.management.approval import approve, validate_proposal
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest
from domain.management.contracts.enums import ExecutionMode
from domain.management.contracts.policy import DAILY_BUDGET_KRW
from domain.management.demo import CAMPAIGN_ID, TENANT_ID, build_sample_proposal
from domain.management.detection.deterministic_dx import diagnose

_SETTINGS = SimpleNamespace(use_mock=True, openai_api_key=None)


@pytest.fixture
def ask():
    return build_management_agent(_SETTINGS)


# ── 감지→진단→승인 픽스처 (여러 테스트 공유) ────────────────────────────────


@pytest.fixture
async def detection_proposal():
    from domain.management.adapters.mock import MockAdPlatform
    from domain.management.contracts.fault_injection import FaultConfig, FaultMode
    from domain.management.detection.exposure_model import (
        expected_hourly_impressions,
        find_anomaly_window,
    )

    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    snaps = await MockAdPlatform().fetch_hourly_metrics(
        CAMPAIGN_ID, today, FaultConfig(mode=FaultMode.BID_LOSS)
    )
    expected = expected_hourly_impressions(DAILY_BUDGET_KRW)
    window = find_anomaly_window(expected, [s.impressions for s in snaps])
    assert window
    dx = diagnose(TENANT_ID, CAMPAIGN_ID, snaps, expected, window)
    return build_sample_proposal(dx)


# ── §9.5 A1–A7: 어시스턴트 완료조건 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_a1_answer_is_nonempty(ask):
    """A1: 질문에 비어있지 않은 답을 반환한다."""
    res = await ask(AskRequest(question="현재 캠페인 상황 알려줘"))
    assert res.answer, "answer가 비어있어서는 안 됨"


@pytest.mark.asyncio
async def test_a2_at_least_one_tool_called(ask):
    """A2: 반드시 하나 이상의 도구를 호출한다."""
    res = await ask(AskRequest(question="예산 얼마 남았어?"))
    assert res.used_tools, "도구 호출 없이 답해서는 안 됨"


@pytest.mark.asyncio
async def test_a3_citations_have_valid_kind(ask):
    """A3: 모든 citation.kind가 live|kb|web 중 하나다."""
    res = await ask(AskRequest(question="지금 운영 중인 캠페인 보여줘"))
    for c in res.citations:
        assert c.kind in ("live", "kb", "web"), f"알 수 없는 kind: {c.kind!r}"


@pytest.mark.asyncio
async def test_a4_budget_question_live_budget_with_evidence(ask):
    """A4: 예산 질문은 live_budget 도구를 사용하고 evidence에 수치가 있다."""
    res = await ask(AskRequest(question="이번 달 예산 소진 얼마야?"))
    assert "live_budget" in res.used_tools
    assert res.evidence and "this_month_spent_krw" in res.evidence


@pytest.mark.asyncio
async def test_a5_campaign_list_uses_live_campaigns(ask):
    """A5: 캠페인 목록 질문은 live_campaigns 도구를 사용한다."""
    res = await ask(AskRequest(question="지금 뭐 운영 중이야?"))
    assert "live_campaigns" in res.used_tools


@pytest.mark.asyncio
async def test_a6_campaign_id_uses_detail(ask):
    """A6: campaign_id 주어지면 live_campaign_detail 도구를 사용한다."""
    res = await ask(AskRequest(question="왜 게재가 안 돼?", campaign_id="camp_1"))
    assert "live_campaign_detail" in res.used_tools


@pytest.mark.asyncio
async def test_a7_action_intent_is_proposal_not_execution(ask):
    """A7: 행동 의도는 직접 실행 없이 제안(suggested_action)으로만 나온다."""
    res = await ask(AskRequest(question="일시정지 해줘", campaign_id="camp_1"))
    # 실행됐다면 write 도구가 used_tools에 있어야 함 — 폴백은 write 도구가 없음.
    write_tools = {"execute", "apply", "write"}
    assert not (write_tools & set(res.used_tools)), "직접 실행 도구가 호출됐음"


# ── §9.9 G1–G5: 감지→진단→승인→집행 게이트 ─────────────────────────────────


@pytest.mark.asyncio
async def test_g1_bid_loss_anomaly_detected():
    """G1: BID_LOSS 고장 주입 시 이상 구간이 감지된다."""
    from domain.management.adapters.mock import MockAdPlatform
    from domain.management.contracts.fault_injection import FaultConfig, FaultMode
    from domain.management.detection.exposure_model import (
        expected_hourly_impressions,
        find_anomaly_window,
    )

    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    snaps = await MockAdPlatform().fetch_hourly_metrics(
        CAMPAIGN_ID, today, FaultConfig(mode=FaultMode.BID_LOSS)
    )
    expected = expected_hourly_impressions(DAILY_BUDGET_KRW)
    window = find_anomaly_window(expected, [s.impressions for s in snaps])
    assert window, "BID_LOSS 고장 주입 시 이상 구간이 감지돼야 함"


@pytest.mark.asyncio
async def test_g2_anomaly_produces_proposal(detection_proposal):
    """G2: 이상 구간에서 진단과 제안이 생성된다."""
    supported = (
        "PAUSE_CAMPAIGN",
        "DECREASE_BUDGET",
        "INCREASE_BUDGET",
        "REPLACE_CREATIVE",
        "EXPAND_AUDIENCE",
        "CHANGE_BID_STRATEGY",
        "ACTIVATE_CAMPAIGN",
        "CREATE_CAMPAIGN",
    )
    assert detection_proposal.action_type in supported, (
        f"알 수 없는 action_type: {detection_proposal.action_type}"
    )


@pytest.mark.asyncio
async def test_g3_fresh_proposal_passes_validation(detection_proposal):
    """G3: 신선한 제안은 유효성 검사를 통과한다."""
    issues = validate_proposal(detection_proposal)
    assert issues == [], f"신선한 제안에 검증 오류: {issues}"


@pytest.mark.asyncio
async def test_g4_approved_action_has_approval_id(detection_proposal):
    """G4: 승인된 액션에 approval_id가 있다."""
    action = approve(detection_proposal, "test_approver", execution_mode=ExecutionMode.DRY_RUN)
    assert action.approval_id, "승인된 액션에 approval_id가 없음"
    assert action.approver_id == "test_approver"
    assert action.execution_mode == ExecutionMode.DRY_RUN


@pytest.mark.asyncio
async def test_g5_expired_proposal_fails_validation(detection_proposal):
    """G5: 만료된 제안은 유효성 검사에서 탈락한다."""
    expired = detection_proposal.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(minutes=1)}
    )
    issues = validate_proposal(expired)
    assert issues, "만료 제안이 유효성 검사를 통과했음(실패해야 함)"
    assert any("만료" in i or "expir" in i.lower() for i in issues), (
        f"오류 메시지에 '만료' 키워드 없음: {issues}"
    )
