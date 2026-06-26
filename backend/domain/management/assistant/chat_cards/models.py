# 채팅 카드 봉투 — 도메인 비종속 섹션 구조. 프론트 범용 렌더러와 백엔드 composer가 공유하는 계약.
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Tone = Literal["neutral", "muted", "success", "warning", "critical"]
CardStatus = Literal["ok", "warning", "critical", "neutral"]

# trace.raw에 담아도 되는 키(스펙 2 대비). 토큰·계정 비밀·대량 row는 영구 제외(루트 규칙).
TRACE_RAW_ALLOWLIST: frozenset[str] = frozenset({"turn_id", "period"})


def filtered_trace_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """allowlist 키만 통과. composer가 trace.raw를 담을 땐 반드시 이 함수만 거친다."""
    return {k: v for k, v in raw.items() if k in TRACE_RAW_ALLOWLIST}


class Badge(BaseModel):
    label: str
    tone: Tone = "neutral"


class MetricItem(BaseModel):
    label: str
    value: str  # 포맷 완료된 표시 문자열 (예 "29,082원")
    hint: str | None = None


class KeyValueItem(BaseModel):
    key: str
    value: str


class Citation(BaseModel):
    kind: str
    source: str
    title: str = ""


class SummarySection(BaseModel):
    kind: Literal["summary"] = "summary"
    title: str | None = None
    text: str


class MetricsSection(BaseModel):
    kind: Literal["metrics"] = "metrics"
    title: str | None = None
    items: list[MetricItem]


class EntitySection(BaseModel):
    kind: Literal["entity"] = "entity"
    title: str | None = None
    items: list[KeyValueItem]


class ProposalSection(BaseModel):
    kind: Literal["proposal"] = "proposal"
    title: str | None = None
    action_type: str
    rationale: str | None = None
    proposal_id: str | None = None
    # 스펙 2 — 미리보기(실행 미연결). 정본 ID(proposal_id) 아님.
    preview_id: str | None = None
    campaign_id: str | None = None  # 스펙3 — finalize 결선용(additive, 없으면 실행 미연결)
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    tier: str | None = None
    executable: bool = False


class ReviewSection(BaseModel):
    kind: Literal["review"] = "review"
    title: str | None = None
    decision: str
    rationale: str | None = None


class EvidenceSection(BaseModel):
    kind: Literal["evidence"] = "evidence"
    title: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)


class EmptyStateSection(BaseModel):
    kind: Literal["empty_state"] = "empty_state"
    title: str | None = None
    text: str


class DiagnosisSection(BaseModel):
    kind: Literal["diagnosis"] = "diagnosis"
    title: str | None = None
    anomaly_type: str
    status: str
    confidence: float
    hypothesis: str = ""


class ExecutionResultSection(BaseModel):
    kind: Literal["execution_result"] = "execution_result"
    title: str | None = None
    action_type: str
    result_status: Literal[
        "success", "submitted_pending_review", "failed", "rejected", "expired", "already_executed"
    ]
    proposal_id: str
    preview_id: str | None = None
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    run_id: str | None = None
    summary: str
    failure_reason: str | None = None


CardSection = Annotated[
    SummarySection
    | MetricsSection
    | EntitySection
    | ProposalSection
    | ReviewSection
    | EvidenceSection
    | EmptyStateSection
    | DiagnosisSection
    | ExecutionResultSection,
    Field(discriminator="kind"),
]


class TraceInfo(BaseModel):
    turn_id: str | None = None
    raw: dict[str, Any] | None = None  # v0 미사용 — 담을 땐 filtered_trace_raw만 거친다


class ChatCard(BaseModel):
    version: Literal[1] = 1
    type: Literal["management", "report", "qa", "generic"] = "management"
    title: str | None = None
    status: CardStatus | None = None
    badges: list[Badge] = Field(default_factory=list)
    sections: list[CardSection]
    trace: TraceInfo | None = None
    # actions: v1 미직렬화 — 변경 액션 실행 정본은 실행 API. 모델에 두지 않는다.
