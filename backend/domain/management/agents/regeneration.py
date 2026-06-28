"""🅱 재생성 agent — 처방 결정 → (시안 필요 시) 4-3 생성 위임·guard → HITL 선택 → ActionProposal.

- Writer 직접 호출 금지 — 산출물은 ActionProposal뿐 (불변 규칙 §4-1).
- B는 시안을 만들지도 채점하지도 않는다 — 생성·순위는 4-3(GeneratorHttpTool), guard만 콘텐츠 게이트.
- 순위 = 4-3 idx 통과(재정렬·채점 없음). 시안 성공 시 rank()가 AWAITING_SELECTION으로 멈추고
  사람 선택 후 package(selected_id)가 제안을 만든다. 시안 불가 시 비크리에이티브 전략으로 fallback.
- 출력은 RemediationOutcome(discriminated) — 절대 예외를 올리지 않는다(top-level try/except→FAILED).
- LangGraph: decide → generate→guard→{select|fallback→{package|END}} / package(direct) / END(noop).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from core.tracing import make_trace_config
from domain.management.agents.outcome import (
    OutcomeError,
    OutcomeKind,
    OutcomeReason,
    RemediationOutcome,
)
from domain.management.agents.selection import SelectionRound
from domain.management.contracts.enums import ActionTier, AnomalyType, ProposalStatus
from domain.management.contracts.policy import DECIDE_CONFIDENCE_MIN, TIER_POLICY
from domain.management.contracts.schemas import (
    ActionProposal,
    CampaignConfig,
    DiagnosisResult,
    finalize_proposal,
)
from domain.management.execution.tier import estimate_max_total_spend

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from langgraph.graph.state import CompiledStateGraph

    from domain.management.agents.selection import SelectionRoundRepository

#: P6 [안] — 재생성 후보 수 상한
MAX_CANDIDATES: Final[int] = 3

#: 금지표현 목록 — 오너 = 🅱 (P6). 과장·기만 광고 카피 차단.
BANNED_EXPRESSIONS: Final[tuple[str, ...]] = (
    "100% 보장",
    "무조건",
    "완치",
    "부작용 없음",
    "전액 환불 보장",
)

#: 크리에이티브가 필요한 처방 — decide 라우팅이 generate 가지로 보낸다.
CREATIVE_ACTIONS: Final[frozenset[str]] = frozenset({"REPLACE_CREATIVE", "CREATE_CAMPAIGN"})


class RiskAppetite(StrEnum):
    """사용자 의향 — 챗봇(입)이 구조화 노브로만 주입 (정보 방화벽 유지).

    "줄이는 건 자율, 늘리는 건 승인" 원칙상 기본값은 보수적(끄기).
    """

    AGGRESSIVE = "aggressive"  # 예산 증액으로 밀어붙임 (Tier 3 승인)
    CONSERVATIVE = "conservative"  # 손절(끄기) (Tier 1 자율)


def decide_action(diagnosis: DiagnosisResult, risk_appetite: RiskAppetite) -> str | None:
    """🅱 처방 결정 코어 — 진단+의향 → action_type (없으면 None=관망).

    diagnosis evidence + 구조화 노브만 읽는다 (그 밖 정보 추론 금지, 방화벽).
    실제 LLM 추론으로 교체 가능한 단일 지점 — 기본은 결정론 (게이트 #9·eval 채점성).
    """
    anomaly = diagnosis.anomaly_type
    if anomaly in (AnomalyType.QUALITY_DEGRADED, AnomalyType.REVIEW_REJECTED):
        return "REPLACE_CREATIVE"
    if anomaly is AnomalyType.AUDIENCE_TOO_NARROW:
        return "CREATE_CAMPAIGN"
    if anomaly in (AnomalyType.BID_LOSS, AnomalyType.BUDGET_EXHAUSTED):
        return "INCREASE_BUDGET" if risk_appetite is RiskAppetite.AGGRESSIVE else "PAUSE_CAMPAIGN"
    # LEARNING_PHASE / REVIEW_DELAY / INCONCLUSIVE / SCHEDULE_GAP → 관망
    return None


# 돈을 늘리는(증액·신규) 처방 — 저확신도면 보류
_SPEND_INCREASING: frozenset[str] = frozenset({"INCREASE_BUDGET", "CREATE_CAMPAIGN"})


def decide_with_confidence(diagnosis: DiagnosisResult, risk_appetite: RiskAppetite) -> str | None:
    """decide_action + 확신도 게이트 — 저확신도면 돈 늘리는 처방을 관망으로 강등."""
    action = decide_action(diagnosis, risk_appetite)
    if action in _SPEND_INCREASING and diagnosis.confidence < DECIDE_CONFIDENCE_MIN:
        return None
    return action


def fallback_action(anomaly: AnomalyType, *, conservative: bool) -> tuple[str | None, bool]:
    """시안 불가 시 비크리에이티브 대체 — (action_type|None, human_review_required).

    근거 없는 direct action 금지 — 원 진단의 근본원인에 맞는 비크리에이티브만.
    """
    if anomaly in (AnomalyType.QUALITY_DEGRADED, AnomalyType.REVIEW_REJECTED):
        return ("PAUSE_CAMPAIGN", False) if conservative else (None, True)
    if anomaly is AnomalyType.AUDIENCE_TOO_NARROW:
        return ("EXPAND_AUDIENCE", False) if conservative else (None, True)
    return (None, False)  # 매핑 없음 → 무제안


#: P3 TTL [안] — 일반 24h (데모 모드는 10분으로 주입)
DEFAULT_PROPOSAL_TTL: Final[timedelta] = timedelta(hours=24)


@dataclass(frozen=True)
class CreativeCandidate:
    candidate_id: str
    copy: dict[str, str] | str  # 4-3 copy 객체 그대로 (B 합성 안 함)
    idx: int | None = None  # 4-3 제공 순위
    image_ref: str | None = None  # s3_key
    explanation: str | None = None  # 4-3 근거
    preview_url: str | None = None


class CreativeGenerationTool(Protocol):
    """광고 생성 툴 (generator 도메인 — 타 팀 인터페이스, 변동 리스크 주의)."""

    async def generate(
        self, diagnosis: DiagnosisResult, count: int
    ) -> Sequence[CreativeCandidate]: ...


class PreviewTool(Protocol):
    async def preview(self, candidate: CreativeCandidate) -> str: ...


@dataclass(frozen=True)
class RemediationContext:
    """제안 패키징에 필요한 실행 맥락 — 오케스트레이터(별도 담당)가 전달."""

    ad_account_id: str
    target_object_ids: tuple[str, ...]
    budget_before_krw: int
    budget_after_krw: int
    run_days: int
    expected_state_version: str
    approval_policy_version: str
    #: 사용자 의향 — decide_action이 예산 가지(증액↔끄기)를 가를 때만 사용.
    risk_appetite: RiskAppetite = RiskAppetite.CONSERVATIVE
    #: None이면 agent가 진단으로 자율 결정(decide_action). 명시하면 그 값으로 override
    #: (PR2 신규 캠페인 등 오케스트레이터 주도 흐름). 어휘 정본 = contracts/policy.py.
    action_type: str | None = None
    # CREATE_CAMPAIGN(신규 캠페인 생성, PR2 옵션 A)일 때만 채운다. 대상 id가 없으므로
    # 오케스트레이터는 target_object_ids=(ad_account_id,)로 두고 설정은 여기로 전달한다.
    campaign_config: CampaignConfig | None = None


def label_action_tier(action_type: str) -> ActionTier:
    """🅱의 제안 라벨 — P1 정책표(TIER_POLICY) 단일 소스 조회.

    판정 정본은 approval.py(🅰)의 judge_tier — 같은 표를 읽으므로 라벨≠판정이
    원칙적으로 발생하지 않는다. 미등록 action_type은 보수적으로 Tier 3.
    """
    return TIER_POLICY.get(action_type, ActionTier.TIER_3)


# ── guard — 유일한 콘텐츠 게이트 (6종 제외) ───────────────────────────


def _copy_text(copy: dict[str, str] | str) -> str:
    if isinstance(copy, str):
        return copy
    return " ".join(filter(None, (copy.get("headline"), copy.get("body"), copy.get("cta"))))


def _asset_mode(candidate: CreativeCandidate, existing_s3_key: str | None) -> str:
    """v1 추론 — candidate 자체 s3_key 있으면 GENERATED_NEW, 없으면 REUSE_EXISTING."""
    return "GENERATED_NEW" if candidate.image_ref else "REUSE_EXISTING"


def _missing_asset(candidate: CreativeCandidate, existing_s3_key: str | None) -> bool:
    """asset 누락 — GENERATED_NEW는 자체 s3_key, REUSE_EXISTING은 기존 s3_key가 있어야 한다."""
    if _asset_mode(candidate, existing_s3_key) == "GENERATED_NEW":
        return not candidate.image_ref
    return not existing_s3_key


def _is_copy_schema_valid(copy: object) -> bool:
    """copy가 구조적으로 유효한지 검사 — 비문자열·비dict 또는 헤드라인·바디·cta가 없는 빈 dict.

    유효: 비어 있지 않은 str, 또는 headline/body/cta 중 하나 이상을 가진 dict.
    무효: 정수·None 등 다른 타입, 또는 세 필드 모두 없는 dict.
    """
    if isinstance(copy, str):
        return True  # 문자열 형식은 구조 유효 (내용 비어 있는지는 empty_copy 규칙이 처리)
    if isinstance(copy, dict):
        return bool(copy.get("headline") or copy.get("body") or copy.get("cta"))
    return False  # 그 외 타입(int, list 등) → 스키마 위반


def guard_candidates(
    candidates: list[CreativeCandidate], *, existing_s3_key: str | None
) -> tuple[list[CreativeCandidate], list[dict[str, str]]]:
    """유일한 콘텐츠 게이트 — 6종 제외. 통과 후보(idx 순서 보존)와 guard_removed(사유) 반환.

    사유 6종:
      1. required_field_missing — candidate_id 없거나 copy=None
      2. schema_invalid — copy가 비문자열·비dict 또는 필수 필드 없는 빈 dict (스펙 §5b)
      3. empty_copy — copy 텍스트가 공백만으로 구성
      4. banned_expression — 금지표현(과장·기만 광고) 포함
      5. duplicate — 동일 copy 텍스트 중복
      6. asset_s3_key_missing — 필요한 s3_key 없음
    """
    kept: list[CreativeCandidate] = []
    removed: list[dict[str, str]] = []
    seen_copy: set[str] = set()
    for c in candidates:
        reason: str | None = None
        if not c.candidate_id or c.copy is None:
            reason = "required_field_missing"
        elif not _is_copy_schema_valid(c.copy):
            reason = "schema_invalid"
        else:
            text = _copy_text(c.copy)
            if not text.strip():
                reason = "empty_copy"
            elif any(b in text for b in BANNED_EXPRESSIONS):
                reason = "banned_expression"
            elif text in seen_copy:
                reason = "duplicate"
            elif _missing_asset(c, existing_s3_key):
                reason = "asset_s3_key_missing"
        if reason is not None:
            removed.append({"candidate_id": c.candidate_id or "", "reason": reason})
            continue
        seen_copy.add(_copy_text(c.copy))
        kept.append(c)
    return kept[:MAX_CANDIDATES], removed


class RemediationState(TypedDict, total=False):
    """LangGraph 상태 — 노드 간 전달되는 값 전부."""

    diagnosis: DiagnosisResult
    context: RemediationContext
    action_type: str | None  # decide가 정한 처방 (None = 관망)
    candidates: list[CreativeCandidate]  # guard 통과 후보 (idx 순서)
    guard_removed: list[dict[str, str]]  # guard에서 제외된 후보 + 사유
    human_review_required: bool  # fallback이 사람 검토를 요구하는가
    fallback: bool  # strategy_fallback 경로를 탔는가
    creative: bool  # 크리에이티브(생성) 가지를 탔는가
    proposal: ActionProposal | None
    generation_fail_reason: OutcomeReason | None  # 생성 실패 사유 (CREATIVE_UNAVAILABLE 분기용)


# v1 한정: rank()가 토큰별로 (진단·context·후보맵)를 메모리에 보관 → package()가 소비.
# 항목은 package() 성공 시 퇴거된다(evicted on successful package()).
# 만료 스윕 없음 — 데모/테스트 전용.
# InMemorySelectionRoundStore와 짝을 이루는 단일 프로세스 데모/테스트 전용 detail.
@dataclass(frozen=True)
class _PendingSelection:
    diagnosis: DiagnosisResult
    context: RemediationContext
    candidates: dict[str, CreativeCandidate]
    guard_removed: list[dict[str, str]]


class RemediationAgent:
    def __init__(
        self,
        *,
        generator: CreativeGenerationTool,
        selection_store: SelectionRoundRepository,
        preview: PreviewTool | None = None,
        max_candidates: int = MAX_CANDIDATES,
        tool_retries: int = 1,
        proposal_ttl: timedelta = DEFAULT_PROPOSAL_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_candidates > MAX_CANDIDATES:
            raise ValueError(f"후보 상한은 {MAX_CANDIDATES}개 (P6)")
        self._generator = generator
        self._selection = selection_store
        self._preview = preview
        self._max_candidates = max_candidates
        self._tool_retries = tool_retries
        self._proposal_ttl = proposal_ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        # v1 한정 — 토큰별 패키징 컨텍스트 (InMemory store와 짝).
        self._pending: dict[str, _PendingSelection] = {}
        self._graph = self._build_graph()

    async def rank(
        self, diagnosis: DiagnosisResult, context: RemediationContext
    ) -> RemediationOutcome:
        """진단 수신 → 그래프 실행 → 종료 상태를 RemediationOutcome으로 분기. 절대 예외 안 올림."""
        try:
            config = make_trace_config(
                domain="management",
                feature="regenerate",
                user_id=diagnosis.tenant_id,
                extra_tags=["part-b"],
                extra_metadata={
                    "tenant_id": diagnosis.tenant_id,
                    "campaign_id": diagnosis.campaign_id,
                    "diagnosis_id": diagnosis.diagnosis_id,
                    "anomaly_type": diagnosis.anomaly_type.value,
                    "ad_account_id": context.ad_account_id,
                },
            )
            state: RemediationState = await self._graph.ainvoke(
                {"diagnosis": diagnosis, "context": context}, config=config
            )
            return await self._to_outcome(diagnosis, context, state)
        except Exception:  # noqa: BLE001 — 어댑터 경계: 모든 예외를 결과로 수렴
            return RemediationOutcome(kind=OutcomeKind.FAILED, error_type=OutcomeError.UNEXPECTED)

    async def package(
        self, selection_token: str, *, tenant_id: str, selected_id: str
    ) -> RemediationOutcome:
        """사람이 고른 후보로 제안을 패키징 — selection_round 검증 후 PROPOSED."""
        try:
            await self._selection.claim(
                selection_token, tenant_id=tenant_id, selected_id=selected_id
            )
        except ValueError:
            return RemediationOutcome(kind=OutcomeKind.INPUT_INVALID)
        pending = self._pending.get(selection_token)
        if pending is None:
            return RemediationOutcome(kind=OutcomeKind.INPUT_INVALID)
        selected = pending.candidates[selected_id]
        proposal = self._package(
            pending.diagnosis,
            pending.context,
            "REPLACE_CREATIVE"
            if pending.context.action_type is None
            else pending.context.action_type,
            candidates=list(pending.candidates.values()),
            selected=selected,
            guard_removed=pending.guard_removed,
        )
        self._pending.pop(selection_token, None)
        return RemediationOutcome(kind=OutcomeKind.PROPOSED, proposal=proposal)

    async def _to_outcome(
        self,
        diagnosis: DiagnosisResult,
        context: RemediationContext,
        state: RemediationState,
    ) -> RemediationOutcome:
        action_type = state.get("action_type")
        proposal = state.get("proposal")
        # direct/fallback action → 이미 package 노드가 proposal을 만들었다.
        if proposal is not None:
            reason: OutcomeReason | None = None
            if state.get("fallback"):
                reason = (
                    OutcomeReason.CREATIVE_FALLBACK_PAUSE
                    if action_type == "PAUSE_CAMPAIGN"
                    else OutcomeReason.CREATIVE_FALLBACK_EXPAND
                )
            return RemediationOutcome(kind=OutcomeKind.PROPOSED, proposal=proposal, reason=reason)
        # noop — 관망
        if action_type is None and not state.get("creative"):
            base = context.action_type or decide_action(diagnosis, context.risk_appetite)
            low_conf = base in _SPEND_INCREASING and diagnosis.confidence < DECIDE_CONFIDENCE_MIN
            return RemediationOutcome(
                kind=OutcomeKind.OBSERVE,
                reason=OutcomeReason.LOW_CONFIDENCE if low_conf else OutcomeReason.ANOMALY_WATCH,
            )
        # creative 가지: guard 통과 후보 ≥1 → AWAITING_SELECTION
        candidates = state.get("candidates", [])
        if candidates:
            token = uuid4().hex
            # self._clock()을 사용해 proposal 타임스탬프와 일관성 유지 + 테스트 동결 clock 지원.
            # claim() 만료 검증은 selection.py가 실시간 wall-clock으로 독자적으로 수행한다.
            now = self._clock()
            rnd = SelectionRound(
                selection_token=token,
                tenant_id=diagnosis.tenant_id,
                candidate_ids=tuple(c.candidate_id for c in candidates),
                expires_at=now + self._proposal_ttl,
                created_at=now,
            )
            await self._selection.save(rnd)
            self._pending[token] = _PendingSelection(
                diagnosis=diagnosis,
                context=context,
                candidates={c.candidate_id: c for c in candidates},
                guard_removed=state.get("guard_removed", []),
            )
            return RemediationOutcome(
                kind=OutcomeKind.AWAITING_SELECTION,
                selection_token=token,
                candidates=[
                    {
                        "candidate_id": c.candidate_id,
                        "idx": c.idx,
                        "copy": c.copy,
                        "explanation": c.explanation,
                        "preview_url": c.preview_url,
                    }
                    for c in candidates
                ],
            )
        # creative 가지인데 생존 후보 0 (생성 빈손 or guard 전멸) → fallback도 action 없음.
        human = bool(state.get("human_review_required"))
        return RemediationOutcome(
            kind=OutcomeKind.CREATIVE_UNAVAILABLE,
            reason=self._unavailable_reason(state),
            human_review_required=human,
        )

    def _unavailable_reason(self, state: RemediationState) -> OutcomeReason:
        # guard가 모두 제거한 경우 — 생성은 성공했으나 콘텐츠 게이트에서 전멸.
        if state.get("guard_removed") and not state.get("generation_fail_reason"):
            return OutcomeReason.GUARD_WIPEOUT
        # 생성 단계에서 실패 사유가 기록된 경우 — 세분화된 코드 반환.
        fail = state.get("generation_fail_reason")
        if fail is not None:
            return fail
        # 예외 없이 빈 목록 반환 — generator가 후보를 내지 못함.
        return OutcomeReason.GENERATOR_EMPTY

    # ── LangGraph 조립 ───────────────────────────────────────────

    def _build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(RemediationState)
        graph.add_node("decide", self._node_decide)
        graph.add_node("generate", self._node_generate)
        graph.add_node("guard", self._node_guard)
        graph.add_node("strategy_fallback", self._node_strategy_fallback)
        graph.add_node("package", self._node_package)
        graph.set_entry_point("decide")
        graph.add_conditional_edges(
            "decide",
            self._route_after_decide,
            {"creative": "generate", "direct": "package", "noop": END},
        )
        graph.add_edge("generate", "guard")
        graph.add_conditional_edges(
            "guard",
            self._route_after_guard,
            {"select": END, "fallback": "strategy_fallback"},
        )
        graph.add_conditional_edges(
            "strategy_fallback",
            self._route_after_fallback,
            {"package": "package", "end": END},
        )
        graph.add_edge("package", END)
        return graph.compile()

    async def _node_decide(self, state: RemediationState) -> RemediationState:
        context = state["context"]
        action_type = context.action_type or decide_with_confidence(
            state["diagnosis"], context.risk_appetite
        )
        return {"action_type": action_type}

    def _route_after_decide(self, state: RemediationState) -> str:
        action_type = state.get("action_type")
        if action_type is None:
            return "noop"  # 관망 — 빈손 복귀
        return "creative" if action_type in CREATIVE_ACTIONS else "direct"

    async def _node_generate(self, state: RemediationState) -> RemediationState:
        candidates, fail_reason = await self._generate(state["diagnosis"])
        return {"candidates": candidates, "creative": True, "generation_fail_reason": fail_reason}

    async def _node_guard(self, state: RemediationState) -> RemediationState:
        existing = state["diagnosis"].evidence_metrics.get("existing_ad_s3_key")
        kept, removed = guard_candidates(state.get("candidates", []), existing_s3_key=existing)
        return {"candidates": kept, "guard_removed": removed}

    def _route_after_guard(self, state: RemediationState) -> str:
        # 생존 후보 ≥1 → rank()가 AWAITING_SELECTION으로 처리 (END에서 멈춤).
        # 0 → 비크리에이티브 전략 fallback.
        return "select" if state.get("candidates") else "fallback"

    async def _node_strategy_fallback(self, state: RemediationState) -> RemediationState:
        anomaly = state["diagnosis"].anomaly_type
        conservative = state["context"].risk_appetite is RiskAppetite.CONSERVATIVE
        action, human = fallback_action(anomaly, conservative=conservative)
        return {"action_type": action, "human_review_required": human, "fallback": True}

    def _route_after_fallback(self, state: RemediationState) -> str:
        return "package" if state.get("action_type") else "end"

    async def _node_package(self, state: RemediationState) -> RemediationState:
        proposal = self._package(
            state["diagnosis"],
            state["context"],
            state["action_type"],
            candidates=[],
            selected=None,
            guard_removed=state.get("guard_removed", []),
        )
        return {"proposal": proposal}

    # ── 노드: 생성 (재시도 1회) ──────────────────────────────────

    async def _generate(
        self, diagnosis: DiagnosisResult
    ) -> tuple[list[CreativeCandidate], OutcomeReason | None]:
        """생성 시도 → (후보 목록, 실패 사유).

        실패 사유는 CREATIVE_UNAVAILABLE 분기에서 세분화된 OutcomeReason으로 사용된다:
        - GeneratorInputError → MISSING_CREATIVE_INPUT
        - TimeoutError → GENERATOR_TIMEOUT
        - 기타 예외 → GENERATOR_UNAVAILABLE
        - 빈 목록(예외 없음) → None (GENERATOR_EMPTY로 처리됨)
        """
        # GeneratorInputError는 regeneration_tools에 정의 — 순환 방지를 위해 런타임 임포트.
        from domain.management.agents.regeneration_tools import (  # noqa: PLC0415
            GeneratorInputError,
        )

        attempts = self._tool_retries + 1
        last_reason: OutcomeReason | None = None
        for attempt in range(attempts):
            try:
                generated = await self._generator.generate(diagnosis, self._max_candidates)
                return list(generated), None
            except GeneratorInputError:
                last_reason = OutcomeReason.MISSING_CREATIVE_INPUT
                break  # 재시도해도 입력 오류는 동일 — 즉시 종료
            except TimeoutError:
                last_reason = OutcomeReason.GENERATOR_TIMEOUT
                if attempt == attempts - 1:
                    break
            except Exception:  # noqa: BLE001 — tool 경계: 복구 시도 후 폴백
                last_reason = OutcomeReason.GENERATOR_UNAVAILABLE
                if attempt == attempts - 1:
                    break
        return [], last_reason

    # ── 노드: ActionProposal 패키징 (🅱 단독 생산) ────────────────

    def _package(
        self,
        diagnosis: DiagnosisResult,
        context: RemediationContext,
        action_type: str,
        *,
        candidates: list[CreativeCandidate],
        selected: CreativeCandidate | None,
        guard_removed: list[dict[str, str]],
    ) -> ActionProposal:
        now = self._clock()
        # 정보 방화벽 — 근거는 진단 evidence + 후보 메타(4-3 통과)만.
        evidence: dict[str, Any] = {**diagnosis.evidence_metrics}
        # 크리에이티브 가지에서만 후보 근거를 싣는다 (예산/끄기는 진단 근거만).
        if selected is not None:
            evidence["candidates"] = [
                {
                    "candidate_id": c.candidate_id,
                    "idx": c.idx,
                    "copy": c.copy,
                    "explanation": c.explanation,
                    "preview_url": c.preview_url,
                }
                for c in candidates
            ]
            evidence["selected_candidate_id"] = selected.candidate_id
        if guard_removed:
            evidence["guard_removed"] = guard_removed
        # 옵션 A — 신규 캠페인 생성은 대상 id가 없어 설정을 evidence_metrics에 싣는다
        # (해시 산식이 evidence를 포함 → 변조 방지 대상에 들어감).
        if action_type == "CREATE_CAMPAIGN" and context.campaign_config is not None:
            evidence["campaign_config"] = context.campaign_config.model_dump(mode="json")
        proposal = ActionProposal(
            proposal_id=str(uuid4()),
            tenant_id=diagnosis.tenant_id,
            ad_account_id=context.ad_account_id,
            target_object_ids=context.target_object_ids,
            action_type=action_type,
            action_tier=label_action_tier(action_type),
            evidence_metrics=evidence,
            metrics_as_of=diagnosis.metrics_as_of,
            hypothesis=diagnosis.hypothesis,
            confidence=diagnosis.confidence,
            expected_state_version=context.expected_state_version,
            budget_before_krw=context.budget_before_krw,
            budget_after_krw=context.budget_after_krw,
            max_total_spend_krw=estimate_max_total_spend(
                context.budget_after_krw, context.run_days
            ),
            expires_at=now + self._proposal_ttl,
            approval_policy_version=context.approval_policy_version,
            status=ProposalStatus.PENDING,
        )
        return finalize_proposal(proposal)
