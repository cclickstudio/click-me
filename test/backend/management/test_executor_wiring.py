# _get_executor 배선 검증 — history_recorder 부착(전역·org)·데모 격리·record_execution 도달
"""부착 여부(hermetic)와 승인 발행→execute()→record_execution 도달(통합형)을 고정한다.

콜백이 '무엇을' 기록하는지는 test_history_link.py, executor가 '언제' 부르는지는
test_history_recorder.py 소관 — 여기는 라우터 배선이 끝까지 이어지는지만 본다.
"""

from datetime import UTC, datetime, timedelta

import pytest
from management.helpers import FakeWriter, make_action, make_proposal

import domain.management.history_link as hl
from api.routers import management as m
from domain.management.contracts.approval_ledger import record_from_action
from domain.management.contracts.enums import ActionTier, ResultStatus
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.contracts.schemas import CampaignConfig


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch):
    """모듈 전역 executor 캐시 초기화 + mock 고정(다른 테스트와 격리)."""
    monkeypatch.setattr(m.settings, "use_mock", True, raising=False)
    m._executor = None
    m._demo_executor_instance = None
    yield
    m._executor = None
    m._demo_executor_instance = None


def test_global_executor_has_history_recorder():
    assert m._get_executor()._history_recorder is not None


def test_org_scoped_executor_has_history_recorder():
    assert m._get_executor(FakeWriter())._history_recorder is not None


def test_demo_executor_has_no_history_recorder():
    # 시연 격리 — 데모 경로는 DB(chat_execution_history)를 건드리지 않는다.
    assert m._demo_executor()._history_recorder is None


async def test_execute_reaches_record_execution(monkeypatch):
    """승인 발행→_get_executor().execute() 성공 시 record_execution까지 도달(스펙 리뷰 P2).

    recorder가 붙어 있어도 기록이 생략되는 회귀(CREATE 역추적 공백류)를 잡는 게 목적 —
    resolve만 fake고 나머지는 실경로(원장 게이트 포함)를 그대로 탄다.
    """
    calls: list[str] = []

    async def _resolve(ids):
        return "proj-1"

    async def _record(pid, feature_type, action, summary, payload=None, user_id=None):
        calls.append(action)

    monkeypatch.setattr(hl, "resolve_project_id", _resolve)
    monkeypatch.setattr(hl, "record_execution", _record)

    now = datetime.now(UTC)
    # 라우터 executor 게이트 정합값 — state_v1(라우터 provider)·실 정책 버전·미만료 시각.
    proposal = make_proposal(
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )
    action = make_action(
        proposal,
        approval_policy_version=APPROVAL_POLICY_VERSION,
        approved_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    await m._APPROVAL_STORE.put(record_from_action(action))  # 원장 발행(게이트 #5)

    result = await m._get_executor(FakeWriter()).execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert calls == ["pause_campaign"]


async def test_execute_create_campaign_reaches_record_execution(monkeypatch):
    """CREATE 제안 실물 형태(campaign_config + snapshot)가 실경로에서 기록까지 도달(계획 리뷰 P2).

    시뮬 기반 형태(source_ad_id 귀속)로 executor CREATE 디스패치(evidence의 campaign_config →
    CampaignConfig → create_full_campaign, executor.py:680)를 그대로 태운다 — PAUSE 도달
    테스트만으로는 CREATE 역추적 공백 회귀를 못 잡는다.
    """
    calls: list[str] = []

    async def _resolve_ad(ad_id):
        return "proj-1" if ad_id else None

    async def _record(pid, feature_type, action, summary, payload=None, user_id=None):
        calls.append(action)

    monkeypatch.setattr(hl, "resolve_project_id_from_ad", _resolve_ad)
    monkeypatch.setattr(hl, "record_execution", _record)

    now = datetime.now(UTC)
    config = CampaignConfig(
        campaign_id="camp_sim_wiring1",
        tenant_id="org-1111",
        ad_account_id="act_001",
        name="시뮬 기반 캠페인",
        objective="traffic",
        daily_budget_krw=50_000,
        start_at=now,
        end_at=now + timedelta(days=7),
    )
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        action_tier=ActionTier.TIER_3,
        target_object_ids=("act_001",),  # 옵션 A — CREATE 대상은 광고계정
        evidence_metrics={
            "campaign_config": config.model_dump(mode="json"),
            "simulation_snapshot": {"source_ad_id": "11111111-1111-1111-1111-111111111111"},
        },
        budget_before_krw=0,
        budget_after_krw=50_000,
        max_total_spend_krw=350_000,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )
    action = make_action(  # TIER_3은 make_action이 proposal에서 tier 승계, approver는 사람
        proposal,
        approval_policy_version=APPROVAL_POLICY_VERSION,
        approved_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    await m._APPROVAL_STORE.put(record_from_action(action))

    result = await m._get_executor(FakeWriter()).execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert calls == ["create_campaign"]
