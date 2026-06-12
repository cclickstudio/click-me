"""🅱 슬라이스 터미널 데모 — 진단 → 재생성 제안 → 승인(스텁) → 실행 → ActionResult 출력.

실행:
    cd backend && uv run python scripts/management_demo.py

🅰 미구현 파트의 대체:
- 진단(detection): 가짜 DiagnosisResult를 직접 만들어 투입
- 승인(approval.py): §8 1주차 운영 원칙의 "동기 즉시승인 스텁"과 동일한 형태로 수동 발급
실행 경로는 전부 실제 코드: RegenerationAgent → Executor → MetaAdsWriter(DRY_RUN).

비용 관리: 결제(토스 테스트 모드) 충전 잔액 = 집행 한도(BudgetAuthority) → 실행 성공 시 차감.
데모에서는 토스 호출만 대역(Fake) — 실제 결제 경로는 FE 위젯 → /api/billing 으로 검증.
"""
# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

from domain.billing.service.billing_service import BillingService
from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.agents.regeneration import (
    CreativeCandidate,
    RegenerationAgent,
    RegenerationContext,
)
from domain.management.contracts.enums import AnomalyType, ExecutionMode
from domain.management.contracts.schemas import ApprovedAction, DiagnosisResult
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import Executor, InMemoryIdempotencyStore
from domain.management.execution.service.execution_service import (
    ExecutionService,
    InMemoryProposalRepository,
)
from domain.management.execution.tier import TenantBudgetRegistry


class DemoToss:
    """토스 confirm 대역 — 실제 호출은 FE 위젯 → /api/billing 경로로 검증."""

    async def confirm(self, payment_key, order_id, amount_krw):
        return {"paymentKey": payment_key, "orderId": order_id, "totalAmount": amount_krw}


class DemoGenerator:
    """생성 tool 스텁 — 7/8 전 generator 팀 인터페이스로 교체."""

    async def generate(self, diagnosis, count):
        return [
            CreativeCandidate(candidate_id=f"cand-{i}", ad_copy=f"새 시안 카피 {i}")
            for i in range(count)
        ]


class DemoScorer:
    """시뮬 점수 tool 스텁 — simulation 팀 인터페이스로 교체."""

    async def score(self, candidate):
        return 0.55 + 0.1 * int(candidate.candidate_id.split("-")[1])


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def main() -> None:
    now = datetime.now(UTC)

    # ── 0) 결제 충전 — 잔액이 곧 집행 한도가 된다 ───────────────
    billing = BillingService(DemoToss())
    order = billing.create_order("org-demo", 500_000)
    await billing.confirm("pay-demo-1", order.order_id, 500_000)
    section("0) 크레딧 충전 (토스 테스트 모드 대역)")
    print(f"충전 금액   : {order.amount_krw:,} KRW")
    print(f"충전 후 잔액: {billing.balance('org-demo'):,} KRW")

    # ── 1) 🅰 진단 대체 입력 (contracts 경유) ──────────────────
    diagnosis = DiagnosisResult(
        diagnosis_id=str(uuid4()),
        tenant_id="org-demo",
        campaign_id="camp-demo-1",
        anomaly_type=AnomalyType.BID_LOSS,
        source="agent",
        hypothesis="입찰 패배로 노출 급감 — 예산 감액 후 재생성 검토",
        confidence=0.82,
        evidence_metrics={"impressions_24h": 120, "expected_impressions_24h": 4800},
        metrics_as_of=now,
        status="CONFIRMED",
    )
    section("1) DiagnosisResult (🅰 대체 입력)")
    print(diagnosis.model_dump_json(indent=2))

    # ── 2) 🅱 재생성 agent → ActionProposal ───────────────────
    agent = RegenerationAgent(generator=DemoGenerator(), scorer=DemoScorer())
    context = RegenerationContext(
        ad_account_id="act_demo",
        target_object_ids=("camp-demo-1",),
        budget_before_krw=50_000,
        budget_after_krw=40_000,  # 감액 → Tier 1 라벨
        run_days=7,
        expected_state_version="sv-1",
        approval_policy_version="approval-policy-v1",
        action_type="adjust_budget",
    )
    proposal = await agent.propose(diagnosis, context)
    assert proposal is not None
    section("2) ActionProposal (🅱 단독 생산)")
    print(proposal.model_dump_json(indent=2))

    # ── 3) 승인 — approval.py(🅰) 자리의 동기 즉시승인 스텁 ────
    action = ApprovedAction(
        approval_id=str(uuid4()),
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.proposal_hash,
        tenant_id=proposal.tenant_id,
        approver_id="AUTO",  # Tier 1 자율 통과
        action_tier=proposal.action_tier,
        approved_at=now,
        expires_at=now + timedelta(minutes=15),
        approval_policy_version="approval-policy-v1",
        expected_state_version="sv-1",
        execution_mode=ExecutionMode.DRY_RUN,
    )
    section("3) ApprovedAction (🅰 승인 스텁 발급)")
    print(action.model_dump_json(indent=2))

    # ── 4) 실행 — 실제 executor + MetaAdsWriter(DRY_RUN) ──────
    audit = InMemoryAuditLog()

    async def state_provider(_ad_account_id: str) -> str:
        return "sv-1"

    # 잔액 = 집행 한도 — billing↔management 연결은 이 합성 지점에서만 (상호 import 없음)
    budgets = TenantBudgetRegistry(default_limit_krw=0)
    budgets.set_limit("org-demo", billing.balance("org-demo"))
    executor = Executor(
        MetaAdsWriter(mode=ExecutionMode.DRY_RUN),
        idempotency=InMemoryIdempotencyStore(),
        audit=audit,
        budget_for=budgets.for_tenant,
        state_version_provider=state_provider,
        current_policy_version="approval-policy-v1",
    )
    repo = InMemoryProposalRepository()
    repo.save(proposal)
    service = ExecutionService(executor, repo, audit)

    result = await service.handle(action)
    section("4) ActionResult ← 터미널에서 받는 최종 결과값")
    print(result.model_dump_json(indent=2))

    # ── 5) 결과의 나머지 수신처 ────────────────────────────────
    section("5) 부수 수신처 — 제안 상태 / 감사 로그 / 멱등 재생")
    print("proposal.status :", repo.get(proposal.proposal_id).status)
    print("audit events    :", [e.category for e in audit.for_approval(action.approval_id)])
    replay = await service.handle(action)  # 같은 승인 재제출
    print("duplicate replay:", replay.result_id == result.result_id, "(같은 result_id 재생)")

    # ── 6) 비용 차감 — 실행 성공분을 크레딧 원장에 기록 ─────────
    section("6) 비용 관리 — 집행 성공분 원장 차감")
    if result.status.value in ("success", "pending_review"):
        spend = proposal.max_total_spend_krw
        if spend > 0:
            billing.record_spend("org-demo", spend, ref_id=action.approval_id)
        print(f"집행 차감   : {spend:,} KRW")
    print(f"차감 후 잔액: {billing.balance('org-demo'):,} KRW")
    for entry in billing.history("org-demo"):
        print(f"  원장: {entry.reason:>6} {entry.delta_krw:+,} → 잔액 {entry.balance_after_krw:,}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 한글 깨짐 방지
    asyncio.run(main())
