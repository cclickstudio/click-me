# 매니지먼트 챗 제안 집행 브릿지 계약 테스트 — FinalizeResult 로컬 계약(스펙3)
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.auth import get_current_user
from core.db import get_db
from domain.management.assistant.contracts import (
    DiagnosisView,
    DiagnosticResult,
    FinalizeResult,
    ProposalPreview,
)
from domain.management.assistant.result_card import build_execution_result_card, map_result_status
from domain.management.contracts.enums import (
    ActionTier,
    FailureReason,
    ProposalStatus,
    ResultStatus,
)
from domain.management.contracts.schemas import ActionResult, verify_proposal_hash
from domain.management.demo import TENANT_ID
from domain.management.execution.proposal_builder import (
    build_action_proposal_from_diagnosis,
    requires_external_approval,
)
from domain.management.execution.service.proposal_store import InMemoryProposalStore


@pytest.fixture(autouse=True)
def _stub_persist_card(monkeypatch):
    # decision 종결마다 _persist_card가 실 DB 세션을 열어 테스트를 오염시키지 않게 기본 no-op.
    # 적재 호출을 관측하는 테스트는 in-test monkeypatch로 이 스텁을 덮어쓴다(나중 적용 우선).
    async def _noop(thread_id, card):
        return None

    monkeypatch.setattr("api.routers.chat_management._persist_card", _noop)


def _ok_anomaly_dx(action="INCREASE_BUDGET", tier="TIER_2"):
    return DiagnosticResult(
        diagnostic_status="ok",
        anomaly=True,
        diagnosis=DiagnosisView(
            anomaly_type="budget_exhausted",
            status="confirmed",
            confidence=0.9,
            hypothesis="예산 소진",
        ),
        proposal_preview=ProposalPreview(
            preview_id="preview_x",
            action_type=action,
            tier=tier,
            budget_before_krw=10000,
            budget_after_krw=15000,
            hypothesis="예산 소진",
        ),
    )


def test_builder_promotes_preview_to_finalized_proposal():
    now = datetime(2026, 6, 25, tzinfo=UTC)
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(),
        tenant_id="org_1",
        ad_account_id="act_1",
        campaign_id="camp_1",
        expected_state_version="state_v1",
        approval_policy_version="v1",
        preview_id="preview_x",
        run_days=7,
        ttl=timedelta(minutes=10),
        now=now,
    )
    assert p.proposal_id != "preview_x"
    assert p.action_type == "INCREASE_BUDGET"
    # 정본 tier는 프리뷰 라벨이 아니라 정책 권위(judge_tier)에서 온다.
    from domain.management.approval import judge_tier

    assert p.action_tier == judge_tier("INCREASE_BUDGET")
    assert p.budget_before_krw == 10000 and p.budget_after_krw == 15000
    assert p.max_total_spend_krw == 15000 * 7
    assert p.status == ProposalStatus.PENDING
    assert p.evidence_metrics.get("preview_id") == "preview_x"
    assert verify_proposal_hash(p)


def test_requires_external_approval_for_tier3():
    assert requires_external_approval(ActionTier.TIER_3) is True
    assert requires_external_approval(ActionTier.TIER_2) is False


def test_finalize_result_finalized_carries_proposal_id():
    r = FinalizeResult(
        status="finalized",
        proposal_id="prop_1",
        action_type="INCREASE_BUDGET",
        tier="TIER_2",
        requires_external_approval=False,
        budget_before_krw=10000,
        budget_after_krw=15000,
        summary="제안 준비됨",
        expires_at="2026-06-25T12:00:00Z",
        drift=False,
    )
    assert r.status == "finalized" and r.proposal_id == "prop_1"


def test_finalize_result_unavailable_needs_no_proposal():
    r = FinalizeResult(status="unavailable", reason="데이터 부족")
    assert r.proposal_id is None


# ── ProposalStore (InMemory 단위) — save/get 왕복·try_claim 원자성·set_status ──


def _make_proposal():
    return build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(),
        tenant_id="org_1",
        ad_account_id="act_1",
        campaign_id="camp_1",
        expected_state_version="state_v1",
        approval_policy_version="v1",
    )


async def test_inmemory_store_save_get_roundtrip():
    from domain.management.execution.service.proposal_store import InMemoryProposalStore

    store = InMemoryProposalStore()
    p = _make_proposal()
    await store.save(p)
    got = await store.get(p.proposal_id)
    assert got is not None
    assert got.proposal_id == p.proposal_id
    assert got.proposal_hash == p.proposal_hash
    assert verify_proposal_hash(got)


async def test_inmemory_try_claim_exactly_once():
    from domain.management.execution.service.proposal_store import InMemoryProposalStore

    store = InMemoryProposalStore()
    p = _make_proposal()
    await store.save(p)
    assert await store.try_claim(p.proposal_id) is True  # PENDING→APPROVED 1회만
    assert await store.try_claim(p.proposal_id) is False  # 더는 PENDING 아님
    claimed = await store.get(p.proposal_id)
    assert claimed is not None and claimed.status == ProposalStatus.APPROVED


async def test_inmemory_set_status_changes_status():
    from domain.management.execution.service.proposal_store import InMemoryProposalStore

    store = InMemoryProposalStore()
    p = _make_proposal()
    await store.save(p)
    await store.set_status(p.proposal_id, ProposalStatus.REJECTED)
    got = await store.get(p.proposal_id)
    assert got is not None and got.status == ProposalStatus.REJECTED


# ── Task 5: 집행 결과 카드 빌더 + 상태 매핑 ──


def test_map_result_status_covers_failure_reasons():
    assert map_result_status(ResultStatus.SUCCESS, None) == "success"
    assert (
        map_result_status(ResultStatus.SUBMITTED_PENDING_REVIEW, None) == "submitted_pending_review"
    )
    assert map_result_status(ResultStatus.REJECTED, None) == "rejected"
    assert map_result_status(ResultStatus.FAILED, FailureReason.PROPOSAL_EXPIRED) == "expired"
    assert (
        map_result_status(ResultStatus.FAILED, FailureReason.STALE_PROPOSAL) == "already_executed"
    )
    assert map_result_status(ResultStatus.FAILED, FailureReason.PLATFORM_ERROR) == "failed"


def test_build_card_from_action_result_and_proposal():
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(),
        tenant_id="org_1",
        ad_account_id="act_1",
        campaign_id="camp_1",
        expected_state_version="state_v1",
        approval_policy_version="v1",
        preview_id="preview_x",
    )
    result = ActionResult(
        result_id="r1", approval_id="ap1", status=ResultStatus.SUCCESS, idempotency_key="idem1"
    )
    card = build_execution_result_card(proposal=p, result=result, run_id=None, turn_id="t1")
    sec = card.model_dump()["sections"][0]
    assert sec["kind"] == "execution_result"
    assert sec["result_status"] == "success"
    assert sec["proposal_id"] == p.proposal_id
    assert sec["preview_id"] == "preview_x"
    assert sec["budget_before_krw"] == 10000 and sec["budget_after_krw"] == 15000
    assert card.status == "ok"


def test_build_card_terminal_without_result():
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(),
        tenant_id="org_1",
        ad_account_id="act_1",
        campaign_id="camp_1",
        expected_state_version="state_v1",
        approval_policy_version="v1",
    )
    card = build_execution_result_card(
        proposal=p, result=None, run_id=None, turn_id="t1", result_status="rejected"
    )
    assert card.model_dump()["sections"][0]["result_status"] == "rejected"
    assert card.status == "neutral"


# ── Task 6: finalize 엔드포인트 (정본 승격 + PENDING 영속) ──


def _fake_user():
    # use_mock=True 경로는 db/org 조회를 건너뛰므로 최소 객체면 충분.
    class _U:
        id = "user_1"

    return _U()


async def test_finalize_persists_pending_and_returns_new_proposal_id(monkeypatch):
    store = InMemoryProposalStore()

    async def fake_diag(settings, campaign_id, tenant_id=None):
        return _ok_anomaly_dx()

    monkeypatch.setattr("api.routers.chat_management.live_diagnosis", fake_diag)
    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post(
                "/api/chat/management/proposals/finalize",
                json={
                    "preview_id": "preview_x",
                    "campaign_id": "camp_1",
                    "thread_id": "mgmt-s1",
                    "shown_budget_after_krw": 15000,
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "finalized"
        assert body["proposal_id"] != "preview_x"
        saved = await store.get(body["proposal_id"])
        assert saved is not None and saved.status.value == "pending"
    finally:
        app.dependency_overrides.clear()


async def test_finalize_unavailable_when_no_anomaly(monkeypatch):
    from domain.management.assistant.contracts import DiagnosticResult

    async def fake_diag(settings, campaign_id, tenant_id=None):
        return DiagnosticResult(diagnostic_status="ok", anomaly=False)

    monkeypatch.setattr("api.routers.chat_management.live_diagnosis", fake_diag)
    monkeypatch.setattr(
        "api.routers.chat_management._get_proposal_store", lambda: InMemoryProposalStore()
    )
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post(
                "/api/chat/management/proposals/finalize",
                json={"campaign_id": "camp_1"},
            )
        assert r.json()["status"] == "no_anomaly"
    finally:
        app.dependency_overrides.clear()


async def test_finalize_and_decision_consistent_for_policy_tier3(monkeypatch):
    # 스펙3 일관성: 프리뷰 라벨이 TIER_2여도 정책상 INCREASE_BUDGET은 TIER_3 →
    # 빌더/finalize/decision이 모두 정책 권위(judge_tier)로 일치한다.
    from domain.management.approval import judge_tier

    # ① 빌더가 정책 tier로 승격 → requires_external_approval True.
    proposal = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(action="INCREASE_BUDGET", tier="TIER_2"),
        tenant_id=TENANT_ID,
        ad_account_id="act_demo",
        campaign_id="camp_1",
        expected_state_version="state_v1",
        approval_policy_version="v1",
    )
    assert proposal.action_tier == judge_tier("INCREASE_BUDGET")
    assert requires_external_approval(proposal.action_tier) is True

    store = InMemoryProposalStore()

    async def fake_diag(settings, campaign_id, tenant_id=None):
        # 프리뷰는 TIER_2 라벨이지만 finalize는 정책 tier를 반영해야 한다.
        return _ok_anomaly_dx(action="INCREASE_BUDGET", tier="TIER_2")

    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r", approval_id="ap", status=ResultStatus.SUCCESS, idempotency_key="x"
        )

    monkeypatch.setattr("api.routers.chat_management.live_diagnosis", fake_diag)
    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            # ② finalize 엔드포인트 — 정책 tier 반영(라벨 "TIER_2"가 아니다).
            fr = await ac.post(
                "/api/chat/management/proposals/finalize",
                json={"preview_id": "preview_x", "campaign_id": "camp_1"},
            )
            assert fr.status_code == 200
            body = fr.json()
            saved = await store.get(body["proposal_id"])
            assert saved is not None
            assert body["requires_external_approval"] is True
            assert body["tier"] == saved.action_tier.name  # 정책 tier 이름 (예: "TIER_3")
            assert body["tier"] == judge_tier("INCREASE_BUDGET").name

            # ③ decision approve → 정책 게이트가 거부, execute 미호출 → finalize와 일관.
            dr = await ac.post(
                f"/api/chat/management/proposals/{body['proposal_id']}/decision",
                json={"decision": "approve", "idempotency_key": "k1"},
            )
        assert dr.status_code == 200
        assert dr.json()["sections"][0]["result_status"] == "rejected"
        assert calls["n"] == 0
    finally:
        app.dependency_overrides.clear()


# ── Task 7: decision 엔드포인트 (approve/reject) — 집행 트리거 ──


def _decision_proposal(action="DECREASE_BUDGET", tier="TIER_1"):
    # FIX #2: 서버 게이트가 judge_tier(action_type)로 정본 Tier를 재도출 →
    # 자동 집행 가능한 happy-path는 정책상 TIER_1인 action_type을 써야 한다.
    # (INCREASE_BUDGET은 TIER_POLICY상 TIER_3 → 게이트에서 reject.)
    return build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(action=action, tier=tier),
        tenant_id=TENANT_ID,
        ad_account_id="act_demo",
        campaign_id="camp_1",
        expected_state_version="state_v1",
        approval_policy_version="v1",
    )


async def test_decision_approve_success(monkeypatch):
    store = InMemoryProposalStore()
    p = _decision_proposal()
    await store.save(p)
    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r",
            approval_id="ap",
            status=ResultStatus.SUCCESS,
            idempotency_key=idempotency_key,
        )

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post(
                f"/api/chat/management/proposals/{p.proposal_id}/decision",
                json={"decision": "approve", "idempotency_key": "k1", "thread_id": "mgmt-s1"},
            )
        assert r.status_code == 200
        card = r.json()
        sec = card["sections"][0]
        assert sec["kind"] == "execution_result"
        assert sec["result_status"] == "success"
        assert calls["n"] == 1
        saved = await store.get(p.proposal_id)
        assert saved is not None and saved.status == ProposalStatus.EXECUTED
    finally:
        app.dependency_overrides.clear()


async def test_decision_approve_expired_not_executed(monkeypatch):
    store = InMemoryProposalStore()
    past = datetime.now(UTC) - timedelta(minutes=1)
    p = _decision_proposal().model_copy(update={"expires_at": past})
    await store.save(p)
    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r", approval_id="ap", status=ResultStatus.SUCCESS, idempotency_key="x"
        )

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post(
                f"/api/chat/management/proposals/{p.proposal_id}/decision",
                json={"decision": "approve", "idempotency_key": "k1"},
            )
        assert r.status_code == 200
        assert r.json()["sections"][0]["result_status"] == "expired"
        assert calls["n"] == 0
    finally:
        app.dependency_overrides.clear()


async def test_decision_reject_idempotent(monkeypatch):
    store = InMemoryProposalStore()
    p = _decision_proposal()
    await store.save(p)
    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r", approval_id="ap", status=ResultStatus.SUCCESS, idempotency_key="x"
        )

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r1 = await ac.post(
                f"/api/chat/management/proposals/{p.proposal_id}/decision",
                json={"decision": "reject", "idempotency_key": "k1"},
            )
            r2 = await ac.post(
                f"/api/chat/management/proposals/{p.proposal_id}/decision",
                json={"decision": "reject", "idempotency_key": "k2"},
            )
        assert r1.json()["sections"][0]["result_status"] == "rejected"
        assert r2.json()["sections"][0]["result_status"] == "rejected"
        assert calls["n"] == 0
        saved = await store.get(p.proposal_id)
        assert saved is not None and saved.status == ProposalStatus.REJECTED
    finally:
        app.dependency_overrides.clear()


async def test_decision_tier3_server_guard(monkeypatch):
    store = InMemoryProposalStore()
    p = _decision_proposal(action="REPLACE_CREATIVE", tier="TIER_3")
    await store.save(p)
    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r", approval_id="ap", status=ResultStatus.SUCCESS, idempotency_key="x"
        )

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post(
                f"/api/chat/management/proposals/{p.proposal_id}/decision",
                json={"decision": "approve", "idempotency_key": "k1"},
            )
        assert r.json()["sections"][0]["result_status"] == "rejected"
        assert calls["n"] == 0
    finally:
        app.dependency_overrides.clear()


async def test_decision_invalid_decision_value_422(monkeypatch):
    # FIX #1: decision은 Literal["approve","reject"] — 그 외 값은 422로 차단, execute 미진입.
    store = InMemoryProposalStore()
    p = _decision_proposal()
    await store.save(p)
    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r", approval_id="ap", status=ResultStatus.SUCCESS, idempotency_key="x"
        )

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post(
                f"/api/chat/management/proposals/{p.proposal_id}/decision",
                json={"decision": "foo", "idempotency_key": "k", "thread_id": "t"},
            )
        assert r.status_code == 422
        assert calls["n"] == 0
    finally:
        app.dependency_overrides.clear()


async def test_decision_concurrent_approve_reject_consistent(monkeypatch):
    # FIX #6: approve+reject 동시 → EXECUTED(execute 1회) 또는 REJECTED(execute 0회), 둘 다 아님.
    store = InMemoryProposalStore()
    p = _decision_proposal()
    await store.save(p)
    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r",
            approval_id="ap",
            status=ResultStatus.SUCCESS,
            idempotency_key=idempotency_key,
        )

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:

            async def _post(decision):
                return await ac.post(
                    f"/api/chat/management/proposals/{p.proposal_id}/decision",
                    json={"decision": decision, "idempotency_key": uuid4().hex},
                )

            await asyncio.gather(_post("approve"), _post("reject"))
        saved = await store.get(p.proposal_id)
        assert saved is not None
        # 정확히 하나만 성립 — 둘 다 아니다.
        if calls["n"] == 1:
            assert saved.status == ProposalStatus.EXECUTED
        else:
            assert calls["n"] == 0
            assert saved.status == ProposalStatus.REJECTED
    finally:
        app.dependency_overrides.clear()


# ── Task 8: 결과 카드 이력 적재 + 세션 재조회 ──


async def test_decision_persists_card_on_terminal_paths(monkeypatch):
    # 모든 종결 경로가 _persist_card를 1회 호출하고, 적재 카드가 HTTP 응답 카드와 동일하다.
    store = InMemoryProposalStore()
    success_p = _decision_proposal(action="DECREASE_BUDGET", tier="TIER_1")  # chat-executable
    reject_p = _decision_proposal(action="REPLACE_CREATIVE", tier="TIER_3")  # Tier3 게이트 거부
    await store.save(success_p)
    await store.save(reject_p)

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        return ActionResult(
            result_id="r", approval_id="ap", status=ResultStatus.SUCCESS, idempotency_key="x"
        )

    collected = []

    async def fake_persist(thread_id, card):
        collected.append((thread_id, card))

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    monkeypatch.setattr("api.routers.chat_management._persist_card", fake_persist)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            ok = await ac.post(
                f"/api/chat/management/proposals/{success_p.proposal_id}/decision",
                json={"decision": "approve", "idempotency_key": "k1", "thread_id": "mgmt-s1"},
            )
            rej = await ac.post(
                f"/api/chat/management/proposals/{reject_p.proposal_id}/decision",
                json={"decision": "approve", "idempotency_key": "k2", "thread_id": "mgmt-s1"},
            )
        assert ok.status_code == 200 and rej.status_code == 200

        # 두 종결 경로 각각 정확히 1건 적재 — 키는 세션 thread_id.
        assert len(collected) == 2
        ok_thread, ok_card = collected[0]
        rej_thread, rej_card = collected[1]
        assert ok_thread == "mgmt-s1" and rej_thread == "mgmt-s1"

        # 적재 카드(ChatCard) == HTTP 응답 카드(JSON), 섹션 kind == execution_result.
        ok_json = ok.json()
        assert ok_json["sections"][0]["kind"] == "execution_result"
        assert ok_json["sections"][0]["result_status"] == "success"
        assert ok_card.model_dump(mode="json") == ok_json

        rej_json = rej.json()
        assert rej_json["sections"][0]["result_status"] == "rejected"
        assert rej_card.model_dump(mode="json") == rej_json
    finally:
        app.dependency_overrides.clear()


def test_content_to_card_round_trip():
    import json

    from api.routers.chat import _content_to_card
    from domain.management.assistant.chat_cards.models import (
        ChatCard,
        ExecutionResultSection,
    )

    card = ChatCard(
        type="management",
        status="ok",
        sections=[
            ExecutionResultSection(
                title="집행 결과",
                action_type="DECREASE_BUDGET",
                result_status="success",
                proposal_id="prop_1",
                summary="집행 완료",
            )
        ],
    )
    content = json.dumps(card.model_dump(mode="json"), ensure_ascii=False)
    assert _content_to_card(content) == card.model_dump(mode="json")
    assert _content_to_card("plain text") is None
    assert _content_to_card(None) is None


async def test_decision_concurrent_exactly_once(monkeypatch):
    store = InMemoryProposalStore()
    p = _decision_proposal()
    await store.save(p)
    calls = {"n": 0}

    async def fake_execute(approved, proposal, idempotency_key, *, db=None, org_id=None):
        calls["n"] += 1
        return ActionResult(
            result_id="r",
            approval_id="ap",
            status=ResultStatus.SUCCESS,
            idempotency_key=idempotency_key,
        )

    monkeypatch.setattr("api.routers.chat_management._get_proposal_store", lambda: store)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:

            async def _one():
                return await ac.post(
                    f"/api/chat/management/proposals/{p.proposal_id}/decision",
                    json={"decision": "approve", "idempotency_key": uuid4().hex},
                )

            responses = await asyncio.gather(*[_one() for _ in range(10)])
        statuses = [r.json()["sections"][0]["result_status"] for r in responses]
        assert calls["n"] == 1
        assert statuses.count("success") == 1
        assert statuses.count("already_executed") == 9
    finally:
        app.dependency_overrides.clear()
