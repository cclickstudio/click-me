"""🤝 contracts — AdPlatformReader / AdPlatformWriter (벤더 중립 Port, D8 확정).

구현체는 ``adapters/<vendor>/`` 드롭인 — contracts 무변경 원칙.
모든 Writer 메서드는 ``idem_key`` 필수 인자 (합의문서 v2.1 §3.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from domain.management.contracts.enums import CampaignState
    from domain.management.contracts.schemas import (
        ActionResult,
        CampaignConfig,
        DeliveryEstimate,
        MetricsSnapshot,
    )


class AdPlatformReader(Protocol):
    """읽기 Port — 🅰 감지·진단이 소비."""

    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot: ...

    async def get_estimate(self, config: CampaignConfig) -> DeliveryEstimate: ...

    async def get_state(self, campaign_id: str) -> CampaignState: ...


class AdPlatformWriter(Protocol):
    """쓰기 Port — 호출 주체는 executor(🅱) 단일 경로뿐 (§4 불변)."""

    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult: ...

    async def adjust_budget(
        self, campaign_id: str, amount_krw: int, idem_key: str
    ) -> ActionResult: ...
