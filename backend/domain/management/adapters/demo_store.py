# 가변 데모 캠페인 스토어 — mock 데모 정본 단일화 + 리밸런스 적용 시 예산 상태화(싱글턴)
"""데모 캠페인 5종의 단일 정본. 라우터(_CAMPAIGNS_DEMO 소비처)와 MockAdPlatform이 함께 읽어
목록·상세·예산 검증이 같은 예산을 보고, DemoBudgetWriter가 적용 성공 시 예산을 갱신해
"제안 → 적용 → 새로고침 시 예산 이동"이 mock에서 완결된다. 구성(이름·상태·고장)은 고정,
예산만 가변 — 프로세스 생애 동안 유지되고 reset()으로 초기화(테스트용).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.management.contracts.enums import CampaignState, ResultStatus
from domain.management.contracts.fault_injection import FaultMode

if TYPE_CHECKING:
    from domain.management.contracts.schemas import ActionResult

# 초기 정본 — 구 api/routers/management.py의 _CAMPAIGNS_DEMO 그대로(이름·상태·예산·고장).
# 일예산 합 100_000 = policy.DAILY_BUDGET_KRW(SMB 데모 표준).
_INITIAL: tuple[tuple[str, str, CampaignState, int, FaultMode | None], ...] = (
    ("camp_1", "여름 신상 원피스", CampaignState.ACTIVE, 40_000, None),
    ("camp_2", "브랜드 데일리 룩", CampaignState.ACTIVE, 25_000, FaultMode.BID_LOSS),
    ("camp_3", "신상 액세서리 모음", CampaignState.ACTIVE, 15_000, FaultMode.AUDIENCE_TOO_NARROW),
    ("camp_4", "쿠폰 안내 공지", CampaignState.UNDER_REVIEW, 10_000, FaultMode.REVIEW_DELAY),
    ("camp_5", "봄 시즌오프 마감", CampaignState.ENDED, 10_000, None),
)

# 모듈 상태 = 싱글턴(단일 프로세스 전제 — mock 데모는 use_mock 단일 워커에서만 쓴다).
_budgets: dict[str, int] = {cid: budget for cid, _name, _state, budget, _fault in _INITIAL}


def campaigns() -> tuple[tuple[str, str, CampaignState, int, FaultMode | None], ...]:
    """데모 캠페인 정본 목록 — 구 _CAMPAIGNS_DEMO와 동일 형태, 예산만 현재 스토어 값."""
    return tuple(
        (cid, name, state, _budgets[cid], fault) for cid, name, state, _budget, fault in _INITIAL
    )


def get_budget(campaign_id: str) -> int:
    """캠페인 현재 일예산(원). 스토어에 없는 id는 0(진입 전 거부 관례와 동일)."""
    return _budgets.get(campaign_id, 0)


def set_budget(campaign_id: str, amount_krw: int) -> None:
    """일예산 갱신 — DemoBudgetWriter가 적용 성공 시 호출."""
    _budgets[campaign_id] = int(amount_krw)


def reset() -> None:
    """초기 정본으로 복원 — 테스트 간 오염 방지용."""
    _budgets.clear()
    _budgets.update({cid: budget for cid, _name, _state, budget, _fault in _INITIAL})


class DemoBudgetWriter:
    """mock writer 래퍼 — adjust_budget 성공 시 스토어 예산을 갱신, 나머지는 inner 위임.

    inner는 DRY_RUN MetaAdsWriter(미전송·계약 검증) — wiring.build_writer(use_mock)가 조립한다.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        result = await self._inner.adjust_budget(campaign_id, amount_krw, idem_key)
        if result.status is ResultStatus.SUCCESS:
            set_budget(campaign_id, amount_krw)
        return result

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)
