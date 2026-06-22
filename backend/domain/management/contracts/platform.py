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
        AccountFunding,
        ActionResult,
        CampaignConfig,
        CampaignInfo,
        CreativePreview,
        DeliveryEstimate,
        DeliveryStatusDetail,
        DemographicMetrics,
        MetricsSnapshot,
        PlatformMetrics,
        RelevanceDiagnostics,
    )


class AdPlatformReader(Protocol):
    """읽기 Port — 🅰 감지·진단이 소비."""

    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot: ...

    async def get_estimate(self, config: CampaignConfig) -> DeliveryEstimate: ...

    async def get_state(self, campaign_id: str) -> CampaignState: ...

    async def list_campaigns(self) -> list[CampaignInfo]: ...

    async def get_platform_breakdown(
        self, campaign_id: str, since: datetime
    ) -> list[PlatformMetrics]: ...

    async def get_demographic_breakdown(
        self, campaign_id: str, since: datetime
    ) -> list[DemographicMetrics]: ...

    async def get_creatives(self, campaign_id: str) -> list[CreativePreview]: ...

    async def get_account_funding(self) -> AccountFunding: ...

    async def get_spend_cap(self, campaign_id: str) -> int | None: ...

    # ── 진단 신호 (meta-data-sources §2②·§3.1) — 성과/품질 진단 agent가 소비 ──
    async def get_relevance_diagnostics(self, campaign_id: str) -> RelevanceDiagnostics: ...

    async def get_delivery_status_detail(self, campaign_id: str) -> DeliveryStatusDetail: ...


class AdPlatformWriter(Protocol):
    """쓰기 Port — 호출 주체는 executor(🅱) 단일 경로뿐 (§4 불변)."""

    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult: ...

    async def adjust_budget(
        self, campaign_id: str, amount_krw: int, idem_key: str
    ) -> ActionResult: ...

    async def replace_creative(
        self, campaign_id: str, creative_id: str, idem_key: str
    ) -> ActionResult: ...

    async def create_campaign(self, config: CampaignConfig, idem_key: str) -> ActionResult: ...

    async def create_full_campaign(self, config: CampaignConfig, idem_key: str) -> ActionResult: ...

    async def set_spend_cap(
        self, campaign_id: str, amount_krw: int, idem_key: str
    ) -> ActionResult: ...

    async def activate_tree(self, campaign_id: str, idem_key: str) -> ActionResult: ...

    async def upload_image(
        self, config: CampaignConfig, image_bytes: bytes, filename: str, idem_key: str
    ) -> str | None: ...

    async def generate_previews(
        self, config: CampaignConfig, image_hash: str, ad_formats: list[str], *, page_id: str
    ) -> list[dict[str, str]]: ...

    async def delete_campaign(self, campaign_id: str, idem_key: str) -> ActionResult: ...

    # ── 에스컬레이션 사다리 신규 액션 (direct, 크리에이티브 없음) ──
    async def expand_audience(self, campaign_id: str, idem_key: str) -> ActionResult: ...

    async def change_bid_strategy(self, campaign_id: str, idem_key: str) -> ActionResult: ...
