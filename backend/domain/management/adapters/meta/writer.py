"""🅱 Meta 쓰기 어댑터 — pause / 예산 / 소재교체 (AdPlatformWriter 구현).

모든 쓰기에 idem_key 필수 (D8). 호출 주체는 executor 단일 경로뿐 (§4 불변).
모드별 의미 (게이팅 §2):
  DRY_RUN          — 요청 빌드만, 미전송 (합성 결과 반환)
  VALIDATE_ONLY    — execution_options=['validate_only']로 실전송, 실제 변경 없음
  LIVE             — 실제 변경(실 게재·실과금). 실 게재 단계 진입으로 정식 허용(§7 갱신).
LIVE 실집행 게이트는 use_mock=False + management_execution_mode=live opt-in이 담당한다.
create_campaign(신규 캠페인 생성)은 PAUSED 상태 객체 생성까지 — 게재는 별도 활성화(activate).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from domain.management.adapters.meta.client import (
    MetaApiError,
    MetaClient,
    build_meta_client,
    normalize_ad_account,
)
from domain.management.contracts.enums import ExecutionMode, FailureReason, ResultStatus
from domain.management.contracts.schemas import ActionResult, CampaignConfig

logger = logging.getLogger(__name__)

#: 실제 Graph API 전송이 일어나는 모드 (DRY_RUN은 로컬 빌드만).
_SENDING_MODES = (ExecutionMode.VALIDATE_ONLY, ExecutionMode.LIVE)

#: CampaignConfig.objective → Meta Outcome 목표(v23 ODAX). 트래픽=클릭, 리드=잠재고객 폼.
_OBJECTIVE_MAP = {"traffic": "OUTCOME_TRAFFIC", "leads": "OUTCOME_LEADS"}

#: 광고세트 최적화 목표(optimization_goal). 캠페인 objective와 짝을 맞춰야 Meta가 거부 안 함.
#: 트래픽=링크클릭 최대화, 리드=잠재고객 폼 제출 최대화.
_ADSET_OPTIMIZATION = {"traffic": "LINK_CLICKS", "leads": "LEAD_GENERATION"}

#: 리드폼 필수 — 개인정보처리방침 링크(이미 운영 중인 페이지).
_PRIVACY_POLICY_URL = "https://clickme.co.kr/privacy"


def _created_id(result: ActionResult) -> str | None:
    """생성 응답에서 Meta가 만든 객체 id를 뽑는다 — 다음 단계의 부모로 넘기기 위함.

    LIVE에선 meta_response={'id': ...}라 id가 잡히고, validate_only/dry_run은 생성이 없어
    id가 없다(None) → 오케스트레이션이 그 단계에서 멈춘다(검증만 하고 체인 X).
    """
    snap = result.platform_response_snapshot or {}
    resp = snap.get("meta_response")
    return resp.get("id") if isinstance(resp, dict) else None


def _tag_campaign(result: ActionResult, cid: str) -> ActionResult:
    """결과 스냅샷에 캠페인 Meta id를 실어, DB 적재가 꺼내 쓰게 한다(오케스트레이션 최종 결과용)."""
    snap = {**(result.platform_response_snapshot or {}), "campaign_meta_id": cid}
    return result.model_copy(update={"platform_response_snapshot": snap})


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
        # 리드폼·광고가 매달릴 페이지(.env META_PAGE_ID). 오케스트레이션 기본 page_id로 쓴다.
        self._page_id: str | None = getattr(settings, "meta_page_id", None)

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
            # KRW는 minor unit 없음(currency_offset=1) — 원 단위 정수를 그대로 전송.
            # 실계정 확인(2026-06-17): act 통화=KRW, min_daily_budget=1521(≈$1.1)이라
            # offset=1 확정(100이면 최소예산이 ₩15로 비현실적). 변환 불필요.
            {"daily_budget": amount_krw},
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
                "name": config.name or f"clickme-{config.campaign_id}",
                "objective": _OBJECTIVE_MAP[config.objective],
                "status": "PAUSED",
                "special_ad_categories": json.dumps(list(config.special_ad_categories)),
                # v21 필수 — 캠페인 예산 미사용 시 true/false 명시 (실 API 검증 2026-06-17).
                # v1은 adset 레벨 예산이므로 false. 누락 시 code=100 sub=4834011.
                "is_adset_budget_sharing_enabled": "false",
            },
            path=f"{normalize_ad_account(config.ad_account_id)}/campaigns",
            ad_account_id=config.ad_account_id,
        )

    async def create_adset(
        self,
        config: CampaignConfig,
        campaign_id: str,
        idem_key: str,
        *,
        page_id: str | None = None,
    ) -> ActionResult:
        """캠페인 산하 광고세트(예산·타겟·최적화) 생성 (Task3). v1은 PAUSED — 사람이 켜야 게재.

        ⚠ campaign_id는 create_campaign이 돌려준 **Meta 캠페인 id**다(로컬 config.campaign_id 아님).
          오케스트레이터가 생성 응답의 id를 받아 이 메서드로 넘긴다.

        목표별 차이.
          - 리드: optimization_goal=LEAD_GENERATION + promoted_object(폼을 띄울 page_id)
            + destination_type=ON_AD(광고 안에서 즉석 양식 노출). page_id 필수.
          - 트래픽: optimization_goal=LINK_CLICKS. promoted_object 불필요.

        인코딩 주의 — client.post는 form 바디(data=)라 중첩 객체(targeting·promoted_object)는
        Graph API 규약대로 **JSON 문자열**로 직렬화해 넣는다(dict 그대로면 깨짐).
        """
        self._require_writable(idem_key)
        if config.objective == "leads" and not page_id:
            # 리드 광고세트는 폼을 띄울 페이지가 필수 — 실 호출 전에 어댑터에서 차단(정직).
            return self._failure(
                "create_adset", campaign_id, idem_key, FailureReason.PLATFORM_ERROR
            )
        # 일정 보정 — Meta는 일예산 광고세트를 "최소 24h 게재 예약" 요구(subcode 1487793).
        # 제안 생성 시각(config.start_at)이 실행 시점엔 과거가 돼 창이 24h 미만이 될 수 있다.
        # → 시작은 항상 미래(now+5분), 종료는 시작+24h 이상으로 보정(여유 10분).
        now = datetime.now(UTC)
        start = config.start_at if config.start_at > now else now + timedelta(minutes=5)
        min_end = start + timedelta(hours=24, minutes=10)
        end = config.end_at if config.end_at > min_end else min_end
        data: dict[str, Any] = {
            "name": f"{config.name or campaign_id}-adset",
            "campaign_id": campaign_id,  # 부모 캠페인(Meta id) — 광고세트가 매달릴 노드
            # 예산은 광고세트 레벨(캠페인은 is_adset_budget_sharing_enabled=false). KRW 원 단위.
            "daily_budget": config.daily_budget_krw,
            "billing_event": "IMPRESSIONS",  # 노출당 과금(표준)
            "optimization_goal": _ADSET_OPTIMIZATION[config.objective],
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",  # 최저비용 자동입찰(상한 없음)
            # 타겟 — 폼에서 받은 위치·연령·성별(config). genders 비면 전체.
            "targeting": json.dumps(
                {
                    "geo_locations": {"countries": list(config.countries)},
                    "age_min": config.age_min,
                    "age_max": config.age_max,
                    **({"genders": list(config.genders)} if config.genders else {}),
                }
            ),
            "status": "PAUSED",  # 안전 — 생성 후 사람이 활성화(Task5)
            "start_time": start.isoformat(),  # 보정된 일정(미래 시작)
            "end_time": end.isoformat(),  # 보정된 일정(시작+24h 이상)
        }
        if config.objective == "leads":
            # 즉석 양식 리드 — 폼을 띄울 페이지 지정 + 광고 안에서(ON_AD) 폼 노출.
            data["promoted_object"] = json.dumps({"page_id": page_id})
            data["destination_type"] = "ON_AD"
        return await self._dispatch(
            "create_adset",
            campaign_id,
            idem_key,
            data,
            path=f"{normalize_ad_account(config.ad_account_id)}/adsets",
            ad_account_id=config.ad_account_id,
        )

    async def create_lead_form(
        self, config: CampaignConfig, idem_key: str, *, page_id: str
    ) -> ActionResult:
        """페이지에 즉석 양식(leadgen form) 생성 (Task4). 사용자가 광고 안에서 채우는 폼.

        엔드포인트는 act_ 아닌 **페이지 노드**(/{page_id}/leadgen_forms). 개인정보처리방침 링크는
        Meta 필수 — 이미 운영 중인 페이지를 쓴다. 질문은 최소(이름·이메일).
        주의 — 폼 생성은 페이지 권한(pages_manage_ads/페이지 토큰)이 필요할 수 있어, live에서
        권한 부족 시 별도 페이지 토큰이 필요할 수 있다(실연동 때 확인).
        """
        self._require_writable(idem_key)
        # 양식은 페이지 자산이라 이름이 페이지 내 유일해야 한다(캠페인 삭제로도 안 지워짐) →
        # 매 생성마다 짧은 고유 접미사를 붙여 "이미 존재하는 이름" 충돌을 막는다.
        form_name = f"{config.name or config.campaign_id}-form-{uuid4().hex[:8]}"
        return await self._dispatch(
            "create_lead_form",
            page_id,
            idem_key,
            {
                "name": form_name,
                "locale": "ko_KR",
                # 중첩 객체는 form 바디라 JSON 문자열로 직렬화.
                "questions": json.dumps([{"type": "FULL_NAME"}, {"type": "EMAIL"}]),
                "privacy_policy": json.dumps(
                    {"url": _PRIVACY_POLICY_URL, "link_text": "개인정보처리방침"}
                ),
                "thank_you_page": json.dumps(
                    {"title": "신청 완료", "body": "곧 연락드리겠습니다.", "button_type": "NONE"}
                ),
            },
            path=f"{page_id}/leadgen_forms",
            ad_account_id=config.ad_account_id,
        )

    async def create_ad(
        self,
        config: CampaignConfig,
        adset_id: str,
        idem_key: str,
        *,
        page_id: str,
        form_id: str,
        image_hash: str | None = None,
    ) -> ActionResult:
        """광고세트에 광고(소재) 생성 (Task4). 리드폼을 여는 CTA가 달린 크리에이티브.

        adset_id는 create_adset이 돌려준 **Meta 광고세트 id**. 크리에이티브의 call_to_action이
        SIGN_UP + lead_gen_form_id로 폼을 띄운다. v1은 PAUSED.
        주의 — link_data는 보통 이미지(image_hash)가 필요하다. 미업로드면 live에서 Meta가
        거부할 수 있어, 이미지 업로드(/adimages)는 후속 Task로 둔다(여기선 있으면 첨부).
        """
        self._require_writable(idem_key)
        link_data: dict[str, Any] = {
            "message": config.name or "지금 신청하세요",
            "link": _PRIVACY_POLICY_URL,  # 리드폼 광고는 CTA가 폼을 띄움 — link는 형식상 필요
            "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": form_id}},
        }
        if image_hash:
            link_data["image_hash"] = image_hash
        creative = {"object_story_spec": {"page_id": page_id, "link_data": link_data}}
        return await self._dispatch(
            "create_ad",
            adset_id,
            idem_key,
            {
                "name": f"{config.name or config.campaign_id}-ad",
                "adset_id": adset_id,
                "creative": json.dumps(creative),
                "status": "PAUSED",
            },
            path=f"{normalize_ad_account(config.ad_account_id)}/ads",
            ad_account_id=config.ad_account_id,
        )

    async def upload_image(
        self, config: CampaignConfig, image_bytes: bytes, filename: str, idem_key: str
    ) -> str | None:
        """이미지를 Meta(/adimages)에 업로드하고 image_hash 반환 — 광고 소재에 첨부할 값.

        전송 모드(live/validate)에서만 실제 업로드. mock/dry는 None(소재 이미지 없이 진행).
        업로드는 캠페인 변경이 아니라 자산 등록이라 과금·게재와 무관(안전).
        """
        self._require_writable(idem_key)
        if self._mode not in _SENDING_MODES or self._client is None:
            return None
        account = normalize_ad_account(config.ad_account_id)
        payload = await self._client.post_image(f"{account}/adimages", image_bytes, filename)
        images = payload.get("images", {})
        entry = images.get(filename) or next(iter(images.values()), {})
        return entry.get("hash") if isinstance(entry, dict) else None

    async def generate_previews(
        self, config: CampaignConfig, image_hash: str, ad_formats: list[str], *, page_id: str
    ) -> list[dict[str, str]]:
        """소재 미리보기(샘플 시안) — 포맷별 Meta 호스팅 iframe HTML. 상태 변경 없음(읽기).

        ad_formats 예: MOBILE_FEED_STANDARD(페이스북 피드)·INSTAGRAM_STANDARD(인스타).
        client 없으면(mock/dry) 빈 목록.
        """
        if self._client is None:
            return []
        account = normalize_ad_account(config.ad_account_id)
        creative = {
            "object_story_spec": {
                "page_id": page_id,
                "link_data": {
                    "message": config.name or "지금 신청하세요",
                    "link": _PRIVACY_POLICY_URL,
                    "image_hash": image_hash,
                },
            }
        }
        out: list[dict[str, str]] = []
        for fmt in ad_formats:
            # generatepreviews는 GET 전용(POST는 subcode 33 거부). creative는 JSON 문자열 쿼리.
            payload = await self._client.get(
                f"{account}/generatepreviews",
                {"creative": json.dumps(creative), "ad_format": fmt},
            )
            data = payload.get("data", [])
            body = data[0].get("body") if data and isinstance(data[0], dict) else None
            if body:
                out.append({"format": fmt, "html": body})
        return out

    async def create_full_campaign(
        self, config: CampaignConfig, idem_key: str, *, page_id: str | None = None
    ) -> ActionResult:
        """오케스트레이션 — 캠페인→광고세트→(리드면 폼→광고)를 한 흐름으로 생성.

        각 단계의 Meta id를 다음 단계의 부모로 넘긴다. **중간 단계가 실패하면 이미 만든 캠페인을
        삭제(롤백)**해 "생성 실패 = 아무것도 안 남음"을 보장한다(부분 생성 방지). 실제 id가 필요해
        LIVE에서 완전 동작하고, validate_only/dry_run은 id가 없어 캠페인 단계까지만 의미가 있다.
        page_id 미지정 시 .env META_PAGE_ID(self._page_id)를 쓴다.
        """
        page_id = page_id or self._page_id
        campaign = await self.create_campaign(config, f"{idem_key}-camp")
        cid = _created_id(campaign)
        if campaign.status is not ResultStatus.SUCCESS or cid is None:
            return campaign  # 검증 모드(또는 캠페인 단계 실패) — 아직 만든 게 없으니 롤백 불요
        adset = await self.create_adset(config, cid, f"{idem_key}-adset", page_id=page_id)
        if adset.status is not ResultStatus.SUCCESS or _created_id(adset) is None:
            await self._rollback(cid, idem_key)
            return adset
        asid = _created_id(adset)
        if config.objective != "leads":
            return _tag_campaign(adset, cid)  # 트래픽은 광고세트까지(광고 소재는 후속)
        form = await self.create_lead_form(config, f"{idem_key}-form", page_id=page_id)
        fid = _created_id(form)
        if form.status is not ResultStatus.SUCCESS or fid is None:
            await self._rollback(cid, idem_key)
            return form
        ad = await self.create_ad(
            config,
            asid,
            f"{idem_key}-ad",
            page_id=page_id,
            form_id=fid,
            image_hash=config.image_hash,  # 업로드된 소재 이미지(있으면 첨부)
        )
        if ad.status is not ResultStatus.SUCCESS:
            await self._rollback(cid, idem_key)
            return ad
        return _tag_campaign(ad, cid)

    async def _rollback(self, campaign_id: str, idem_key: str) -> None:
        """부분 생성 정리 — 이미 만든 캠페인(과 하위 광고세트·광고)을 삭제. 실패해도 흐름은 진행.

        삭제 자체가 또 실패하면 고아 객체가 남을 수 있으나 모두 PAUSED라 과금은 0(로그로 알린다).
        """
        try:
            await self.delete_campaign(campaign_id, f"{idem_key}-rollback")
            logger.warning("부분 생성 롤백 — 캠페인 삭제 %s", campaign_id)
        except Exception:  # noqa: BLE001 — 롤백 실패가 원래 에러를 가리지 않게
            logger.warning("롤백 실패 — 수동 정리 필요 campaign=%s", campaign_id)

    async def activate(self, object_id: str, idem_key: str) -> ActionResult:
        """객체(캠페인/광고세트/광고)를 ACTIVE로 — 게재·과금 시작 (Task5).

        ⚠ 실제 과금이 시작되는 유일한 쓰기. 게재되려면 캠페인·광고세트·광고가 **모두 ACTIVE**여야
          한다(한 단계라도 PAUSED면 미게재). 단일 객체만 켠다 — 트리 전체는 activate_tree 참고.
        """
        self._require_writable(idem_key)
        return await self._dispatch("activate", object_id, idem_key, {"status": "ACTIVE"})

    async def set_spend_cap(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        """캠페인 평생 지출 상한(spend_cap)을 건다 — 충전 크레딧만큼만 집행되게 하는 핵심.

        Meta는 누적 지출이 spend_cap에 도달하면 캠페인 게재를 자동 중지한다(= "소진 시 자동 종료").
        KRW는 minor unit 없음(offset=1)이라 원 단위 정수를 그대로 전송한다.
        """
        self._require_writable(idem_key)
        if amount_krw <= 0:
            raise ValueError("spend_cap은 양의 KRW 정수여야 함")
        return await self._dispatch(
            "set_spend_cap",
            campaign_id,
            idem_key,
            {"spend_cap": amount_krw},
            spend_cap=amount_krw,
        )

    async def activate_tree(self, campaign_id: str, idem_key: str) -> ActionResult:
        """캠페인·광고세트·광고를 **모두 ACTIVE**로 — 실제 게재가 시작되는 진입점.

        한 단계라도 PAUSED면 미게재이므로 자식(광고세트·광고)을 조회해 전부 켠다. 어느 단계든
        실패하면 그 결과를 반환하고 멈춘다. DRY_RUN(클라이언트 없음)은 캠페인 단계만 합성 처리.
        """
        self._require_writable(idem_key)
        camp = await self.activate(campaign_id, f"{idem_key}-camp")
        if camp.status is not ResultStatus.SUCCESS:
            return _tag_campaign(camp, campaign_id)
        # DRY_RUN 등 비전송 모드는 자식이 실재하지 않으므로 캠페인 단계까지만(검증).
        if self._mode not in _SENDING_MODES or self._client is None:
            return _tag_campaign(camp, campaign_id)
        for prefix, path in (("adset", f"{campaign_id}/adsets"), ("ad", f"{campaign_id}/ads")):
            for i, child_id in enumerate(await self._child_ids(path)):
                result = await self.activate(child_id, f"{idem_key}-{prefix}-{i}")
                if result.status is not ResultStatus.SUCCESS:
                    return _tag_campaign(result, campaign_id)
        return _tag_campaign(camp, campaign_id)

    async def _child_ids(self, path: str) -> list[str]:
        """캠페인 하위 객체(adsets/ads)의 id 목록 — 조회 실패는 빈 목록으로 흡수."""
        try:
            payload = await self._client.get(path, {"fields": "id", "limit": 200})  # type: ignore[union-attr]
        except (httpx.HTTPError, MetaApiError):
            logger.warning("자식 id 조회 실패: %s", path)
            return []
        return [str(row["id"]) for row in payload.get("data", []) if row.get("id")]

    async def delete_campaign(self, campaign_id: str, idem_key: str) -> ActionResult:
        """캠페인 삭제 (HTTP DELETE) — 자식 광고세트·광고도 함께 삭제. 되돌릴 수 없음.

        파괴적 작업이라 **LIVE에서만 실제 삭제**한다(VALIDATE_ONLY는 delete에 검증 플래그가
        없어 진짜 지워지므로, 안전하게 LIVE 외 모드는 무동작 dry_run으로 본다).
        """
        self._require_writable(idem_key)
        if self._mode is not ExecutionMode.LIVE or self._client is None:
            return self._result("delete_campaign", campaign_id, idem_key, dry_run=True)
        try:
            response = await self._client.delete(campaign_id)
        except httpx.TimeoutException:
            return self._failure("delete_campaign", campaign_id, idem_key, FailureReason.TIMEOUT)
        except MetaApiError as exc:
            reason = (
                FailureReason.RATE_LIMITED if exc.is_rate_limited else FailureReason.PLATFORM_ERROR
            )
            logger.warning("Meta 삭제 실패 [delete_campaign] code=%s: %s", exc.code, exc)
            return self._failure("delete_campaign", campaign_id, idem_key, reason)
        except httpx.HTTPError as exc:
            logger.warning("Meta 삭제 HTTP 오류 [delete_campaign]: %s", type(exc).__name__)
            return self._failure(
                "delete_campaign", campaign_id, idem_key, FailureReason.PLATFORM_ERROR
            )
        return self._result(
            "delete_campaign", campaign_id, idem_key, dry_run=False, response=response
        )

    async def expand_audience(self, campaign_id: str, idem_key: str) -> ActionResult:
        """타겟 범위 확장 (에스컬레이션 1순위). v1은 adset targeting 확장 요청 빌드 수준.

        실 Meta에선 adset의 targeting(geo/age/interest) 완화 — v1은 detailed_targeting_expansion을
        켜는 수준으로 한정 (§7 좁히기). DRY_RUN은 요청만 빌드.
        """
        self._require_writable(idem_key)
        return await self._dispatch(
            "expand_audience",
            campaign_id,
            idem_key,
            {"targeting_optimization": "expansion_all"},
        )

    async def change_bid_strategy(self, campaign_id: str, idem_key: str) -> ActionResult:
        """입찰 전략 변경 (에스컬레이션 2순위). 예산 총액 불변 — 전략만 전환.

        실 Meta에선 campaign bid_strategy 전환(LOWEST_COST_WITHOUT_CAP 등) — v1은 요청 빌드 수준.
        DRY_RUN은 요청만 빌드.
        """
        self._require_writable(idem_key)
        return await self._dispatch(
            "change_bid_strategy",
            campaign_id,
            idem_key,
            {"bid_strategy": "LOWEST_COST_WITHOUT_CAP"},
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
        validate_only = self._mode is ExecutionMode.VALIDATE_ONLY
        # 플랫폼 예외를 Port의 FailureReason으로 번역 — executor가 어댑터 비의존으로
        # 재시도(TIMEOUT/RATE_LIMITED)를 판단하게 한다(번역 책임은 어댑터에 둔다).
        try:
            response = await self._client.post(post_path, data, validate_only=validate_only)
        except httpx.TimeoutException:
            return self._failure(operation, campaign_id, idem_key, FailureReason.TIMEOUT, **detail)
        except MetaApiError as exc:
            reason = (
                FailureReason.RATE_LIMITED if exc.is_rate_limited else FailureReason.PLATFORM_ERROR
            )
            # 진단용 서버 로그 — 어느 단계(operation)에서 Meta가 왜 거부했는지. exc 메시지엔
            # 토큰 미포함(MetaApiError 설계). API 응답엔 reason + 사용자용 안내(error_user_msg)만.
            logger.warning("Meta 쓰기 실패 [%s] code=%s: %s", operation, exc.code, exc)
            # error_user_msg는 Meta가 주는 사람용 설명(토큰·기밀 없음) → 프론트에 그대로 표시 가능.
            if exc.user_msg:
                detail["user_msg"] = exc.user_msg
            return self._failure(operation, campaign_id, idem_key, reason, **detail)
        except httpx.HTTPError as exc:
            logger.warning("Meta 쓰기 HTTP 오류 [%s]: %s", operation, type(exc).__name__)
            return self._failure(
                operation, campaign_id, idem_key, FailureReason.PLATFORM_ERROR, **detail
            )
        return self._result(
            operation, campaign_id, idem_key, dry_run=validate_only, response=response, **detail
        )

    def _failure(
        self,
        operation: str,
        campaign_id: str,
        idem_key: str,
        reason: FailureReason,
        **detail: int | str,
    ) -> ActionResult:
        # 메시지엔 토큰/응답 바디를 싣지 않는다(게이트 #8) — reason만으로 충분.
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",
            status=ResultStatus.FAILED,
            failure_reason=reason,
            platform_response_snapshot={
                "mode": str(self._mode),
                "operation": operation,
                "campaign_id": campaign_id,
                **detail,
            },
            executed_at=datetime.now(UTC),
            idempotency_key=idem_key,
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
