# 챗 오케스트레이터 I/O 계약 — 슈퍼바이저↔서브에이전트 교환 스키마(영속 DTO schemas.py와 분리).
from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class Route(StrEnum):
    GENERAL = "general"
    MANAGEMENT = "management"
    SIMULATION = "simulation"
    GENERATION = "generation"
    CLARIFY = "clarify"  # 모호한 교차 요청 — 위임 대신 사용자에게 되묻기


class Citation(BaseModel):
    # management/assistant/contracts.py:Citation과 구조 동일(의도적 분리). 통합 시 core 승격 검토.
    kind: str  # kb | live
    source: str
    title: str = ""


class ChatTurnRequest(BaseModel):
    """한 챗 턴 입력 — 라우터가 ChatRequest에서 변환."""

    session_id: uuid.UUID
    user_text: str
    history: list[dict] = Field(default_factory=list)  # [{role, content}] 숏텀 윈도우
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    context_ad_id: str | None = None
    context_campaign_id: str | None = None
    context_simulation_id: str | None = None
    context_ad_image_url: str | None = None  # 채팅 첨부 이미지(시뮬 트리거 VLM 입력)
    context_ad_image_key: str | None = None  # S3 영구 식별자(DB 영속)


class ProposedAction(BaseModel):
    """승인 카드 표면 + ActionProposal 재구성 정보(매니지먼트 집행 브릿지)."""

    action_type: str
    target_campaign_id: str | None = None
    tier: str
    requires_approval: bool
    rationale: str
    budget_after_krw: int | None = None
    run_days: int = 7


class SubAgentRequest(BaseModel):
    # 단발 위임 — 슈퍼바이저가 history를 question/context_ids에 녹여 전달(서브에이전트는 무상태).
    question: str
    context_ids: dict = Field(default_factory=dict)
    knobs: dict = Field(default_factory=dict)
    history: list[dict] = Field(
        default_factory=list
    )  # [{role, content}] 최근 윈도우(어댑터가 프리앰블화)


class SubAgentResult(BaseModel):
    route: Route
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    structured: dict = Field(default_factory=dict)  # → `result` SSE 프레임 {kind, data}
    proposed_action: ProposedAction | None = None
    error: str | None = None
