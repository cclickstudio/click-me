"""🅱 Meta 쓰기 어댑터 — pause / 예산 / 생성 / 미리보기 (stub, Should 스코프).

모든 쓰기에 idem_key 필수 (D8). 호출 주체는 executor 단일 경로뿐.
LIVE 쓰기는 7/8 스코프 제외(Won't) — DRY_RUN은 "실제 API 계약 검증" 수준까지만.
Meta 실연동이 하루 이상 막히면 철수하고 Mock 완성도로 전환 (§8 운영 원칙).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from domain.management.contracts.enums import ExecutionMode, ResultStatus
from domain.management.contracts.schemas import ActionResult, CampaignConfig


class MetaAdsWriter:
    """AdPlatformWriter 구현 stub — wiring.py가 Port에 꽂는다."""

    def __init__(self, settings: object = None, *, mode: ExecutionMode | None = None) -> None:
        configured = getattr(settings, "management_execution_mode", None)
        self._mode = mode or (ExecutionMode(configured) if configured else ExecutionMode.DRY_RUN)

    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult:
        self._require_writable(idem_key)
        return self._dry_run_result("pause", campaign_id, idem_key)

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        self._require_writable(idem_key)
        if amount_krw < 0:
            raise ValueError("KRW 음수 금지")
        return self._dry_run_result("adjust_budget", campaign_id, idem_key, amount_krw=amount_krw)

    async def create_ad(self, config: CampaignConfig, idem_key: str) -> ActionResult:
        """생성 stub — Port v2 후보 (D8 Port에는 미포함, 계약 개정 절차 필요)."""
        self._require_writable(idem_key)
        return self._dry_run_result("create_ad", config.campaign_id, idem_key)

    async def preview(self, campaign_id: str) -> str:
        """미리보기 stub — 읽기성이라 idem_key 불요."""
        return f"https://www.facebook.com/ads/preview/{campaign_id}"

    def _require_writable(self, idem_key: str) -> None:
        if not idem_key:
            raise ValueError("모든 쓰기에 idem_key 필수 (D8)")
        if self._mode is ExecutionMode.LIVE:
            raise NotImplementedError("LIVE 쓰기는 7/8 스코프 제외 (Won't, §7)")

    def _dry_run_result(
        self, operation: str, campaign_id: str, idem_key: str, **detail: int
    ) -> ActionResult:
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",  # 어댑터는 승인 맥락을 모름 — executor가 최종 결과로 재포장
            status=ResultStatus.SUCCESS,
            platform_response_snapshot={
                "dry_run": self._mode is not ExecutionMode.LIVE,
                "mode": str(self._mode),
                "operation": operation,
                "campaign_id": campaign_id,
                **detail,
            },
            executed_at=datetime.now(UTC),
            idempotency_key=idem_key,
        )
