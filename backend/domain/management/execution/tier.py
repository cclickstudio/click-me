"""🅱 예산 권한 — remaining_authority + 90/95% 소프트캡 + 사전 비용 견적 (P4).

하드캡 = 내부 권한 한도이며 플랫폼 지출 절대상한 보장이 아님 (v1.3 §7 승계).
Tier 매핑표(action_type → ActionTier)의 판정 정본은 approval.py(🅰) —
여기는 예산 축의 강제만 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

WARN_THRESHOLD: Final[float] = 0.90
ESCALATE_THRESHOLD: Final[float] = 0.95


class BudgetDecision(StrEnum):
    """P4 소프트캡 [안]: 90% 경고 / 95% 자율 불가(사용자 승인 필요) / 100% 차단."""

    ALLOW = "allow"
    WARN = "warn"
    ESCALATE = "escalate"
    BLOCK = "block"


def estimate_max_total_spend(budget_after_krw: int, run_days: int) -> int:
    """P4 산식 [안]: budget_after × 집행 예상일수.

    계산 주체 = 🅱 제안 시점 / 검증 주체 = executor 6)단계 — 같은 함수를 공유한다.
    """
    if budget_after_krw < 0:
        raise ValueError("KRW 음수 금지")
    return budget_after_krw * max(run_days, 1)


@dataclass
class BudgetAuthority:
    """데모 예산 권한 — 영속화 전 인메모리. limit 기본값은 P4 [빈칸] 합의 후 확정."""

    limit_krw: int
    spent_krw: int = 0

    def evaluate(self, additional_krw: int) -> BudgetDecision:
        if additional_krw < 0:
            raise ValueError("KRW 음수 금지")
        if self.limit_krw <= 0:
            return BudgetDecision.BLOCK
        projected = self.spent_krw + additional_krw
        if projected > self.limit_krw:
            return BudgetDecision.BLOCK
        ratio = projected / self.limit_krw
        if ratio >= ESCALATE_THRESHOLD:
            return BudgetDecision.ESCALATE
        if ratio >= WARN_THRESHOLD:
            return BudgetDecision.WARN
        return BudgetDecision.ALLOW

    def commit(self, amount_krw: int) -> None:
        """실행 성공 후에만 호출 — 거부·실패 건은 권한을 소모하지 않는다."""
        if amount_krw < 0:
            raise ValueError("KRW 음수 금지")
        self.spent_krw += amount_krw


class TenantBudgetRegistry:
    """tenant_id → BudgetAuthority — 멀티테넌트 정렬 (한 tenant가 남의 한도를 못 쓴다).

    영속화 전 인메모리. 한도 영속·tenant별 커스텀 한도는 core 테이블 합의 후.
    """

    def __init__(self, default_limit_krw: int) -> None:
        self._default_limit_krw = default_limit_krw
        self._authorities: dict[str, BudgetAuthority] = {}

    def for_tenant(self, tenant_id: str) -> BudgetAuthority:
        if tenant_id not in self._authorities:
            self._authorities[tenant_id] = BudgetAuthority(limit_krw=self._default_limit_krw)
        return self._authorities[tenant_id]
