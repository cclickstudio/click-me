"""🅱 재생성 agent — 멀티툴(생성·시뮬·미리보기) → 모든 ActionProposal 패키징 (단독 생산).

- Writer 직접 호출 금지 — 산출물은 ActionProposal뿐 (불변 규칙 §4-1).
- 후보 가드: 최대 3개(P6) · 금지표현(오너=🅱) · 점수 미달 제거.
- tool 실패는 재시도 1회 후 해당 후보 폴백(제외) — 빈손 복귀가 무리한 제안보다 낫다.
- LangGraph StateGraph: generate → guard → score →(생존자 있으면)→ package.
  실제 tool(생성·시뮬·미리보기)은 타 팀 인터페이스 확정 전까지 Protocol 주입.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from domain.management.contracts.enums import ActionTier, AnomalyType, ProposalStatus
from domain.management.contracts.policy import TIER_POLICY
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

DEFAULT_MIN_SCORE: Final[float] = 0.5

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


#: P3 TTL [안] — 일반 24h (데모 모드는 10분으로 주입)
DEFAULT_PROPOSAL_TTL: Final[timedelta] = timedelta(hours=24)


@dataclass(frozen=True)
class CreativeCandidate:
    candidate_id: str
    ad_copy: str
    image_ref: str | None = None
    sim_score: float | None = None
    preview_url: str | None = None


class CreativeGenerationTool(Protocol):
    """광고 생성 툴 (generator 도메인 — 타 팀 인터페이스, 변동 리스크 주의)."""

    async def generate(
        self, diagnosis: DiagnosisResult, count: int
    ) -> Sequence[CreativeCandidate]: ...


class SimulationScoreTool(Protocol):
    """시뮬레이션 점수 툴 — 시뮬 점수 ↔ 실성과 상관 미검증 (발표 공개 한계, §7)."""

    async def score(self, candidate: CreativeCandidate) -> float: ...


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


class RemediationState(TypedDict, total=False):
    """LangGraph 상태 — 노드 간 전달되는 값 전부."""

    diagnosis: DiagnosisResult
    context: RemediationContext
    action_type: str | None  # decide가 정한 처방 (None = 관망)
    candidates: list[CreativeCandidate]
    survivors: list[CreativeCandidate]
    best: CreativeCandidate | None
    proposal: ActionProposal | None


class RemediationAgent:
    def __init__(
        self,
        *,
        generator: CreativeGenerationTool,
        scorer: SimulationScoreTool,
        preview: PreviewTool | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
        max_candidates: int = MAX_CANDIDATES,
        tool_retries: int = 1,
        proposal_ttl: timedelta = DEFAULT_PROPOSAL_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_candidates > MAX_CANDIDATES:
            raise ValueError(f"후보 상한은 {MAX_CANDIDATES}개 (P6)")
        self._generator = generator
        self._scorer = scorer
        self._preview = preview
        self._min_score = min_score
        self._max_candidates = max_candidates
        self._tool_retries = tool_retries
        self._proposal_ttl = proposal_ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._graph = self._build_graph()

    async def propose(
        self, diagnosis: DiagnosisResult, context: RemediationContext
    ) -> ActionProposal | None:
        """진단 수신 → (LangGraph) 생성 → 가드 → 채점 → 최선 후보로 패키징."""
        final: RemediationState = await self._graph.ainvoke(
            {"diagnosis": diagnosis, "context": context}
        )
        return final.get("proposal")

    # ── LangGraph 조립 ───────────────────────────────────────────

    def _build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(RemediationState)
        graph.add_node("decide", self._node_decide)
        graph.add_node("generate", self._node_generate)
        graph.add_node("guard", self._node_guard)
        graph.add_node("score", self._node_score)
        graph.add_node("package", self._node_package)
        graph.set_entry_point("decide")
        graph.add_conditional_edges(
            "decide",
            self._route_after_decide,
            {"creative": "generate", "direct": "package", "noop": END},
        )
        graph.add_edge("generate", "guard")
        graph.add_edge("guard", "score")
        graph.add_conditional_edges(
            "score",
            self._route_after_score,
            {"package": "package", "end": END},  # 생존자 0 → 빈손 복귀
        )
        graph.add_edge("package", END)
        return graph.compile()

    async def _node_decide(self, state: RemediationState) -> RemediationState:
        context = state["context"]
        action_type = context.action_type or decide_action(
            state["diagnosis"], context.risk_appetite
        )
        return {"action_type": action_type}

    def _route_after_decide(self, state: RemediationState) -> str:
        action_type = state.get("action_type")
        if action_type is None:
            return "noop"  # 관망 — 빈손 복귀
        return "creative" if action_type in CREATIVE_ACTIONS else "direct"

    async def _node_generate(self, state: RemediationState) -> RemediationState:
        return {"candidates": await self._generate(state["diagnosis"])}

    async def _node_guard(self, state: RemediationState) -> RemediationState:
        return {"candidates": self._guard(state["candidates"])}

    async def _node_score(self, state: RemediationState) -> RemediationState:
        scored = await self._score_all(state["candidates"])
        survivors = [c for c in scored if (c.sim_score or 0.0) >= self._min_score]
        best = max(survivors, key=lambda c: c.sim_score or 0.0) if survivors else None
        if best is not None:
            best = await self._attach_preview(best)
            # 미리보기가 제안 evidence에 실리도록 생존자 목록에도 반영
            survivors = [best if c.candidate_id == best.candidate_id else c for c in survivors]
        return {"survivors": survivors, "best": best}

    def _route_after_score(self, state: RemediationState) -> str:
        return "package" if state.get("best") is not None else "end"

    async def _node_package(self, state: RemediationState) -> RemediationState:
        proposal = self._package(
            state["diagnosis"],
            state["context"],
            state["action_type"],
            state.get("best"),
            state.get("survivors", []),
        )
        return {"proposal": proposal}

    # ── 노드 1: 생성 (재시도 1회) ────────────────────────────────

    async def _generate(self, diagnosis: DiagnosisResult) -> list[CreativeCandidate]:
        attempts = self._tool_retries + 1
        for attempt in range(attempts):
            try:
                generated = await self._generator.generate(diagnosis, self._max_candidates)
                return list(generated)
            except Exception:  # noqa: BLE001 — tool 경계: 복구 시도 후 폴백
                if attempt == attempts - 1:
                    return []
        return []

    # ── 노드 2: 가드 (금지표현 + 상한) ───────────────────────────

    def _guard(self, candidates: list[CreativeCandidate]) -> list[CreativeCandidate]:
        passed = [
            c for c in candidates if not any(banned in c.ad_copy for banned in BANNED_EXPRESSIONS)
        ]
        return passed[: self._max_candidates]

    # ── 노드 3: 시뮬 채점 (실패 후보는 폴백 제외) ─────────────────

    async def _score_all(self, candidates: list[CreativeCandidate]) -> list[CreativeCandidate]:
        scored: list[CreativeCandidate] = []
        for candidate in candidates:
            for attempt in range(self._tool_retries + 1):
                try:
                    score = await self._scorer.score(candidate)
                except Exception:  # noqa: BLE001 — tool 경계: 복구 시도 후 폴백
                    if attempt == self._tool_retries:
                        break
                else:
                    scored.append(
                        CreativeCandidate(
                            candidate_id=candidate.candidate_id,
                            ad_copy=candidate.ad_copy,
                            image_ref=candidate.image_ref,
                            sim_score=score,
                            preview_url=candidate.preview_url,
                        )
                    )
                    break
        return scored

    async def _attach_preview(self, candidate: CreativeCandidate) -> CreativeCandidate:
        if self._preview is None:
            return candidate
        try:
            url = await self._preview.preview(candidate)
        except Exception:  # noqa: BLE001 — 미리보기는 부가 정보: 실패해도 제안은 진행
            return candidate
        return CreativeCandidate(
            candidate_id=candidate.candidate_id,
            ad_copy=candidate.ad_copy,
            image_ref=candidate.image_ref,
            sim_score=candidate.sim_score,
            preview_url=url,
        )

    # ── 노드 4: ActionProposal 패키징 (🅱 단독 생산) ─────────────

    def _package(
        self,
        diagnosis: DiagnosisResult,
        context: RemediationContext,
        action_type: str,
        best: CreativeCandidate | None,
        survivors: list[CreativeCandidate],
    ) -> ActionProposal:
        now = self._clock()
        # 정보 방화벽 — 근거는 진단 evidence + 후보 점수만 (그 밖 정보로 추론 금지)
        evidence: dict[str, Any] = {**diagnosis.evidence_metrics}
        # 크리에이티브 가지에서만 후보 근거를 싣는다 (예산/끄기는 진단 근거만).
        if best is not None:
            evidence["candidates"] = [
                {
                    "candidate_id": c.candidate_id,
                    "sim_score": c.sim_score,
                    "preview_url": c.preview_url,
                }
                for c in survivors
            ]
            evidence["selected_candidate_id"] = best.candidate_id
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
