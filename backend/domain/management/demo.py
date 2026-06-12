"""🅰 슬라이스 터미널 데모 — 감지 → 진단 → 승인(HITL) → ApprovedAction 발행.

실행:  cd backend && uv run python -m domain.management.demo
옵션:  --fault {bid_loss,review_rejected,none}  주입할 고장 (기본 bid_loss)
       --yes                                    HITL 프롬프트 없이 자동 승인 (CI용)

LLM 호출 없음 (결정론 경로) — API 키·비용 불필요. Meta 연결 없이 전체 사이클 재현.
ApprovedAction 발행에서 멈춘다: 여기서부터가 🅱 영역(executor)이다.
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel

from domain.management.adapters.mock import MockAdPlatform
from domain.management.approval import (
    approve,
    relabel_if_mismatch,
    requires_human,
    validate_proposal,
)
from domain.management.contracts.enums import ActionTier, ProposalStatus
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.policy import (
    APPROVAL_POLICY_VERSION,
    DAILY_BUDGET_KRW,
    PROPOSAL_TTL_MINUTES,
)
from domain.management.contracts.schemas import (
    ActionProposal,
    DiagnosisResult,
    MetricsSnapshot,
    finalize_proposal,
)
from domain.management.detection.deterministic_dx import diagnose
from domain.management.detection.exposure_model import (
    expected_hourly_impressions,
    find_anomaly_window,
)

TENANT_ID = "org_demo"
CAMPAIGN_ID = "camp_demo_2841"


def _header(step: str, title: str) -> None:
    print(f"\n{'═' * 64}\n {step}  {title}\n{'═' * 64}")


def _print_json(model: BaseModel) -> None:
    print(json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2))


def _print_chart(expected: list[float], snapshots: list[MetricsSnapshot]) -> None:
    peak = max(expected)
    for hour, (exp, snap) in enumerate(zip(expected, snapshots, strict=True)):
        ratio = snap.impressions / exp if exp else 0.0
        bar = "█" * round(min(snap.impressions / peak, 1.0) * 24)
        marker = "⚠" if ratio < 0.5 else " "
        print(
            f"  {hour:>2}시 │{bar:<24}│ {ratio * 100:>4.0f}%"
            f"  기대 {exp:>6,.0f} → 관측 {snap.impressions:>6,} {marker}"
        )


def build_sample_proposal(dx: DiagnosisResult) -> ActionProposal:
    """🅱가 보낼 ActionProposal 예시 — 데모용. 실제 생산자는 🅱 단독 (v2.0 ⑤).

    의도적으로 Tier 1로 잘못 라벨링해 승인 플레인의 재라벨 판정을 시연한다.
    """
    proposal = ActionProposal(
        proposal_id=f"prop_{uuid4().hex[:8]}",
        tenant_id=dx.tenant_id,
        ad_account_id="act_demo_001",
        target_object_ids=[dx.campaign_id],
        action_type="INCREASE_BUDGET",
        action_tier=ActionTier.TIER_1,  # 잘못된 라벨 — 정책 판정은 Tier 3
        evidence_metrics=dx.evidence_metrics,
        metrics_as_of=dx.metrics_as_of,
        hypothesis=dx.hypothesis,
        confidence=dx.confidence,
        expected_state_version="state_v1",
        budget_before_krw=DAILY_BUDGET_KRW,
        budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
        max_total_spend_krw=int(DAILY_BUDGET_KRW * 1.5) * 7,
        expires_at=datetime.now(UTC) + timedelta(minutes=PROPOSAL_TTL_MINUTES),
        approval_policy_version=APPROVAL_POLICY_VERSION,
        status=ProposalStatus.PENDING,
    )
    return finalize_proposal(proposal)


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description="🅰 감지·진단·승인 플레인 터미널 데모")
    parser.add_argument(
        "--fault", choices=["bid_loss", "review_rejected", "none"], default="bid_loss"
    )
    parser.add_argument("--yes", action="store_true", help="HITL 프롬프트 없이 자동 승인")
    args = parser.parse_args()

    fault = None if args.fault == "none" else FaultConfig(mode=FaultMode(args.fault))
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1) Mock 게재 생성 — 고장 주입 = eval 정답 라벨
    fault_label = fault.mode.value if fault else "없음 (정상 게재)"
    _header("1/5", f"Mock 게재 데이터 생성 — 고장 주입: {fault_label}")
    snapshots = MockAdPlatform().fetch_hourly_metrics(CAMPAIGN_ID, today, fault)
    expected = expected_hourly_impressions(DAILY_BUDGET_KRW)
    _print_chart(expected, snapshots)

    # 2) 감지 — 기대 곡선 vs 관측 (2회 연속 관측 가드레일)
    _header("2/5", "감지 — 기대 노출(일중 곡선) vs 관측")
    window = find_anomaly_window(expected, [s.impressions for s in snapshots])
    if not window:
        print("  이상 없음 — 정상 게재로 판정, 종료합니다.")
        return
    print(f"  이상 구간: {window[0]}시~{window[-1]}시 ({len(window)}시간, 2회 연속 관측 충족)")

    # 3) 결정론 진단 → DiagnosisResult (contracts)
    _header("3/5", "결정론 진단 → DiagnosisResult (🅰 → 🅱 계약)")
    dx = diagnose(TENANT_ID, CAMPAIGN_ID, snapshots, expected, window)
    _print_json(dx)

    # 4) 승인 플레인 — Tier 판정 + HITL
    _header("4/5", "승인 플레인 (approval.py) — Tier 판정 + HITL")
    proposal = build_sample_proposal(dx)
    print(f"  제안 수신: {proposal.action_type} (제안 라벨: Tier {proposal.action_tier})")

    issues = validate_proposal(proposal)
    if issues:
        print("  승인 전 검증 실패:", *issues, sep="\n   - ")
        return
    print("  승인 전 3단계 검증 통과 (만료 / 해시 / 정책 버전)")

    proposal, relabeled = relabel_if_mismatch(proposal)
    if relabeled:
        print(f"  ⚠ 정책 판정: Tier {proposal.action_tier} — 라벨≠판정, 재라벨 후 진행 (감사 기록)")

    if requires_human(proposal.action_tier):
        budget_msg = f"₩{proposal.budget_before_krw:,} → ₩{proposal.budget_after_krw:,}"
        print(f"\n  ★ Tier {proposal.action_tier} — 사용자 승인 필요 (예산 증액: {budget_msg})")
        answer = "y" if args.yes else input("  승인하시겠습니까? [y/N] ").strip().lower()
        if answer != "y":
            print("\n  거절됨 — REJECTED 기록 후 종료. (무승인 액션은 Writer에 도달 불가)")
            return
        approver = "user_kku1031"
    else:
        print(f"  Tier {proposal.action_tier} — 자율 통과 (approver=AUTO)")
        approver = "AUTO"

    # 5) ApprovedAction 발행 — 여기서부터 🅱
    _header("5/5", "ApprovedAction 발행 (승인 TTL 5분) → 여기서부터 🅱 (executor)")
    _print_json(approve(proposal, approver))
    print(
        "\n  → 🅱 executor가 이 계약을 받아 4단계 재검증(해시·만료·상태버전·한도) 후\n"
        "    멱등키를 선점하고 실행한다. 모든 지출은 executor 단일 경로 (불변 규칙 #1)."
    )


if __name__ == "__main__":
    main()
