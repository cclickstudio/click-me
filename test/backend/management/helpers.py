"""🅱 테스트 공용 헬퍼 — contracts만 import (🅰 내부 import 금지, 불변 규칙 §4-3)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.management.adapters.meta.writer import synthetic_creative_id
from domain.management.contracts.enums import (
    ActionTier,
    ExecutionMode,
    FailureReason,
    FaultMode,
    ProposalStatus,
    ResultStatus,
)
from domain.management.contracts.schemas import (
    ActionProposal,
    ActionResult,
    ApprovedAction,
    FaultConfig,
    finalize_proposal,
)
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import (
    DEFAULT_ALLOWED_MODES,
    Executor,
    InMemoryIdempotencyStore,
)
from domain.management.execution.tier import BudgetAuthority

NOW = datetime(2026, 6, 12, 9, 0, 0, tzinfo=UTC)
POLICY_VERSION = "approval-policy-v1"
STATE_VERSION = "sv-42"


def make_proposal(**overrides) -> ActionProposal:
    fields = {
        "proposal_id": str(uuid4()),
        "tenant_id": "org-1111",
        "ad_account_id": "act_001",
        "target_object_ids": ("camp-001",),
        "action_type": "PAUSE_CAMPAIGN",
        "action_tier": ActionTier.TIER_1,
        "evidence_metrics": {"ctr": 0.001},
        "metrics_as_of": NOW,
        "hypothesis": "입찰 패배로 노출 급감",
        "confidence": 0.8,
        "expected_state_version": STATE_VERSION,
        "budget_before_krw": 50_000,
        "budget_after_krw": 50_000,
        "max_total_spend_krw": 0,
        "expires_at": NOW + timedelta(hours=24),
        "approval_policy_version": POLICY_VERSION,
        "status": ProposalStatus.PENDING,
    }
    fields.update(overrides)
    return finalize_proposal(ActionProposal(**fields))


def make_action(proposal: ActionProposal, **overrides) -> ApprovedAction:
    fields = {
        "approval_id": str(uuid4()),
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "tenant_id": proposal.tenant_id,
        "approver_id": "user-77",
        "action_tier": proposal.action_tier,
        "approved_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
        "approval_policy_version": POLICY_VERSION,
        "expected_state_version": proposal.expected_state_version,
        "execution_mode": ExecutionMode.MOCK,
    }
    fields.update(overrides)
    return ApprovedAction(**fields)


class FakeWriter:
    """FaultConfig(contracts)로 고장을 켜는 가짜 Writer — Mock(🅰 소유)과 무관."""

    def __init__(
        self,
        fault: FaultConfig | None = None,
        fail_times: int = 0,
        fail_targets: set[str] | None = None,
    ):
        self.fault = fault
        self.fail_times = fail_times  # 처음 N회만 고장, 이후 성공
        self.fail_targets = fail_targets or set()
        self.calls: list[tuple[str, str, str]] = []  # (op, campaign_id, idem_key)

    async def pause(self, campaign_id: str, idem_key: str) -> ActionResult:
        return self._respond("PAUSE_CAMPAIGN", campaign_id, idem_key)

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        return self._respond("INCREASE_BUDGET", campaign_id, idem_key)

    async def replace_creative(self, ad_id: str, creative_id: str, idem_key: str) -> ActionResult:
        return self._respond("REPLACE_CREATIVE", ad_id, idem_key)

    async def create_ad_creative(
        self, ad_account_id: str, *, image_hash, headline, body, link_url, idem_key: str
    ) -> str:
        if not idem_key:
            raise ValueError("idem_key 필수")
        self.calls.append(("create_ad_creative", ad_account_id, idem_key))
        return synthetic_creative_id(idem_key)  # real writer와 동일 digest(리뷰 P2-3)

    async def replace_creative_tree(
        self,
        campaign_id: str,
        *,
        ad_ids,
        ad_account_id,
        image_hash,
        headline,
        body,
        link_url,
        idem_key: str,
    ) -> ActionResult:
        # real writer 부분실패 동작 반영(리뷰 P2-b) — fail_targets에 든 ad에서 실패하고
        # succeeded_ad_ids/failed_ad_id snapshot을 남긴다(executor 부분실패·재시도 테스트용).
        # real writer와 동일하게 ad_ids 선검증(P1-2·P1-1 — str은 list/tuple 아니라 차단).
        if (
            not isinstance(ad_ids, (list, tuple))
            or not ad_ids
            or not all(isinstance(a, str) and a for a in ad_ids)
        ):
            raise ValueError("replace_creative_tree: ad_ids는 비어있지 않은 문자열 리스트여야 함")
        creative_id = await self.create_ad_creative(
            ad_account_id,
            image_hash=image_hash,
            headline=headline,
            body=body,
            link_url=link_url,
            idem_key=f"{idem_key}-creative",
        )
        succeeded: list[str] = []
        for i, ad_id in enumerate(ad_ids):  # 결속 ad_ids 각각 기록(fan-out 검증용)
            r = self._respond("REPLACE_CREATIVE", ad_id, f"{idem_key}-ad-{i}")
            if r.status is not ResultStatus.SUCCESS:
                # real writer와 동일하게 일부 성공 후 실패면 PARTIAL_FAILURE(코드리뷰 #1) —
                # executor가 결과를 박제하고 멱등키를 풀지 않게 한다.
                failure_reason = FailureReason.PARTIAL_FAILURE if succeeded else r.failure_reason
                return r.model_copy(
                    update={
                        "failure_reason": failure_reason,
                        "platform_response_snapshot": {
                            **(r.platform_response_snapshot or {}),
                            "succeeded_ad_ids": succeeded,
                            "failed_ad_id": ad_id,
                            "creative_id": creative_id,
                        },
                    }
                )
            succeeded.append(ad_id)
        # real writer 성공 snapshot과 같은 키(creative_id·ad_count·succeeded_ad_ids) 반환.
        ok = self._respond("REPLACE_CREATIVE", campaign_id, idem_key)
        return ok.model_copy(
            update={
                "platform_response_snapshot": {
                    **(ok.platform_response_snapshot or {}),
                    "creative_id": creative_id,
                    "ad_count": len(ad_ids),
                    "succeeded_ad_ids": succeeded,
                }
            }
        )

    async def create_campaign(self, config, idem_key: str) -> ActionResult:
        return self._respond("CREATE_CAMPAIGN", config.campaign_id, idem_key)

    async def create_full_campaign(self, config, idem_key: str) -> ActionResult:
        # 오케스트레이션은 executor 입장에선 단일 CREATE_CAMPAIGN 액션 — 기록 라벨 동일.
        return self._respond("CREATE_CAMPAIGN", config.campaign_id, idem_key)

    async def delete_campaign(self, campaign_id: str, idem_key: str) -> ActionResult:
        return self._respond("DELETE_CAMPAIGN", campaign_id, idem_key)

    async def upload_image(self, config, image_bytes, filename: str, idem_key: str) -> str | None:
        return "fakehash123"

    async def generate_previews(self, config, image_hash, ad_formats, *, page_id):
        return [{"format": f, "html": f"<iframe data-fmt='{f}'></iframe>"} for f in ad_formats]

    async def expand_audience(self, campaign_id: str, idem_key: str) -> ActionResult:
        return self._respond("EXPAND_AUDIENCE", campaign_id, idem_key)

    async def change_bid_strategy(self, campaign_id: str, idem_key: str) -> ActionResult:
        return self._respond("CHANGE_BID_STRATEGY", campaign_id, idem_key)

    def _respond(self, op: str, campaign_id: str, idem_key: str) -> ActionResult:
        self.calls.append((op, campaign_id, idem_key))
        if campaign_id in self.fail_targets:
            return self._failure(idem_key, FailureReason.PLATFORM_ERROR)
        if self.fault is not None and self.fail_times > 0:
            self.fail_times -= 1
            if self.fault.mode is FaultMode.WRITE_TIMEOUT:
                return self._failure(idem_key, FailureReason.TIMEOUT)
            if self.fault.mode is FaultMode.RATE_LIMITED:
                return self._failure(idem_key, FailureReason.RATE_LIMITED)
            if self.fault.mode is FaultMode.REVIEW_STUCK:
                return ActionResult(
                    result_id=str(uuid4()),
                    approval_id="",
                    idempotency_key=idem_key,
                    status=ResultStatus.SUBMITTED_PENDING_REVIEW,
                    executed_at=NOW,
                )
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",
            idempotency_key=idem_key,
            status=ResultStatus.SUCCESS,
            executed_at=NOW,
            platform_response_snapshot={"op": op, "campaign_id": campaign_id},
        )

    def _failure(self, idem_key: str, reason: FailureReason) -> ActionResult:
        return ActionResult(
            result_id=str(uuid4()),
            approval_id="",
            idempotency_key=idem_key,
            status=ResultStatus.FAILED,
            failure_reason=reason,
            executed_at=NOW,
        )


async def _no_sleep(_seconds: float) -> None:
    return None


def build_executor(
    writer: FakeWriter,
    *,
    limit_krw: int = 1_000_000,
    state_version: str = STATE_VERSION,
    policy: str = POLICY_VERSION,
    now: datetime = NOW,
    approvals=None,  # 승인 원장(게이트 #5) — None이면 게이트 생략(기존 테스트 호환)
    allow_live: bool = False,  # LIVE opt-in — 기본 executor는 LIVE 불허(EXECUTION_MODE_DISABLED)
):
    """executor + 인메모리 의존성 일괄 조립. (executor, audit, idem, budget) 반환."""

    async def state_provider(_ad_account_id: str) -> str:
        return state_version

    audit = InMemoryAuditLog()
    idem = InMemoryIdempotencyStore()
    budget = BudgetAuthority(limit_krw=limit_krw)
    allowed = (
        (*DEFAULT_ALLOWED_MODES, ExecutionMode.LIVE) if allow_live else DEFAULT_ALLOWED_MODES
    )
    executor = Executor(
        writer,
        idempotency=idem,
        audit=audit,
        budget_for=lambda _tenant_id: budget,
        state_version_provider=state_provider,
        current_policy_version=policy,
        allowed_modes=allowed,
        clock=lambda: now,
        sleep=_no_sleep,
        approvals=approvals,
    )
    return executor, audit, idem, budget
