"""🅱 Meta 쓰기 어댑터 — pause / 예산 / 소재교체 (AdPlatformWriter 구현).

모든 쓰기에 idem_key 필수 (D8). 호출 주체는 executor 단일 경로뿐 (§4 불변).
모드별 의미 (게이팅 §2):
  DRY_RUN          — 요청 빌드만, 미전송 (합성 결과 반환)
  SANDBOX_CONTRACT — execution_options=['validate_only']로 실전송, 실제 변경 없음
  LIVE             — 실제 변경. 코드 경로는 존재하나 executor 허용 모드 밖이라 봉인됨.
LIVE 봉인은 executor.DEFAULT_ALLOWED_MODES + use_mock 이중 게이트가 담당한다.
create_campaign(신규 캠페인 생성, PR2)은 v1에서 PAUSED 상태 객체 생성까지만 (§7 좁히기).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from domain.management.adapters.meta.client import MetaClient, build_meta_client
from domain.management.contracts.enums import ExecutionMode, ResultStatus
from domain.management.contracts.schemas import ActionResult, CampaignConfig

#: 실제 Graph API 전송이 일어나는 모드 (DRY_RUN은 로컬 빌드만).
_SENDING_MODES = (ExecutionMode.SANDBOX_CONTRACT, ExecutionMode.LIVE)


class MetaAdsWriter:
    """AdPlatformWriter 구현 — wiring.py가 Port에 꽂는다."""

    def __init__(
        self,
        settings: object = None,
        *,
        mode: ExecutionMode | None = None,
        client: MetaClient | None = None,
    ) -> None:
        configured = getattr(settings, "management_execution_mode", None)
        self._mode = mode or (ExecutionMode(configured) if configured else ExecutionMode.DRY_RUN)
        # 전송 모드 + 토큰이 있을 때만 클라이언트를 구성한다. 토큰이 없으면 클라이언트
        # 없이 합성 결과로 폴백 — 오설정(모드만 LIVE/SANDBOX, 자격증명 없음)이 실수로
        # 네트워크를 때리지 않게 한다 (instagram.py의 "토큰 없으면 미전송" 관례와 동일).
        if client is not None:
            self._client: MetaClient | None = client
        elif self._mode in _SENDING_MODES and getattr(settings, "meta_access_token", None):
            self._client = build_meta_client(settings)
        else:
            self._client = None

    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult:
        self._require_writable(idem_key)
        return await self._dispatch("pause", campaign_id, idem_key, {"status": "PAUSED"})

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        self._require_writable(idem_key)
        if amount_krw < 0:
            raise ValueError("KRW 음수 금지")
        return await self._dispatch(
            "adjust_budget",
            campaign_id,
            idem_key,
            {"daily_budget": amount_krw},  # 계정 통화 = KRW 전제 (정수, minor unit 없음)
            amount_krw=amount_krw,
        )

    async def replace_creative(
        self, campaign_id: str, creative_id: str, idem_key: str
    ) -> ActionResult:
        """재생성 agent(🅱)가 고른 selected_candidate_id를 게재에 반영.

        실 Meta에선 Ad 객체의 creative 갱신 — v1은 대상에 creative 참조를 거는 수준.
        """
        self._require_writable(idem_key)
        return await self._dispatch(
            "replace_creative",
            campaign_id,
            idem_key,
            {"creative": {"creative_id": creative_id}},
            creative_id=creative_id,
        )

    async def create_campaign(self, config: CampaignConfig, idem_key: str) -> ActionResult:
        """신규 캠페인 생성 (PR2). v1은 PAUSED 상태로만 만든다 — 생성 후 사람이 켜야 게재(안전).

        Meta는 campaign→adset→ad 3단이지만 v1은 campaign 객체 생성까지로 한정 (§7 좁히기).
        """
        self._require_writable(idem_key)
        return await self._dispatch(
            "create_campaign",
            config.campaign_id,
            idem_key,
            {
                "name": f"clickme-{config.campaign_id}",
                "objective": "OUTCOME_TRAFFIC",  # v1 트래픽(클릭) 목표
                "status": "PAUSED",
                "special_ad_categories": "[]",
            },
            path=f"act_{config.ad_account_id}/campaigns",
            ad_account_id=config.ad_account_id,
        )

    async def preview(self, campaign_id: str) -> str:
        """미리보기 stub — 읽기성이라 idem_key 불요."""
        return f"https://www.facebook.com/ads/preview/{campaign_id}"

    # ── 내부 ─────────────────────────────────────────────────────

    def _require_writable(self, idem_key: str) -> None:
        if not idem_key:
            raise ValueError("모든 쓰기에 idem_key 필수 (D8)")

    async def _dispatch(
        self,
        operation: str,
        campaign_id: str,
        idem_key: str,
        data: dict[str, Any],
        *,
        path: str | None = None,
        **detail: int | str,
    ) -> ActionResult:
        # path 미지정 시 대상 자체가 경로 (pause/예산/소재교체). create는 act_{id}/campaigns.
        post_path = path or campaign_id
        if self._mode not in _SENDING_MODES or self._client is None:
            # DRY_RUN(또는 클라이언트 미구성) — 전송 없이 요청만 빌드한 것으로 본다.
            return self._result(operation, campaign_id, idem_key, dry_run=True, **detail)
        validate_only = self._mode is ExecutionMode.SANDBOX_CONTRACT
        response = await self._client.post(post_path, data, validate_only=validate_only)
        return self._result(
            operation, campaign_id, idem_key, dry_run=validate_only, response=response, **detail
        )

    def _result(
        self,
        operation: str,
        campaign_id: str,
        idem_key: str,
        *,
        dry_run: bool,
        response: dict[str, Any] | None = None,
        **detail: int | str,
    ) -> ActionResult:
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",  # 어댑터는 승인 맥락을 모름 — executor가 최종 결과로 재포장
            status=ResultStatus.SUCCESS,
            platform_response_snapshot={
                "dry_run": dry_run,
                "mode": str(self._mode),
                "operation": operation,
                "campaign_id": campaign_id,
                "meta_response": response,
                **detail,
            },
            executed_at=datetime.now(UTC),
            idempotency_key=idem_key,
        )
