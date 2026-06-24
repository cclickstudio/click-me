# 매니지먼트 어시스턴트 I/O 계약 — 질문/근거+인용 답변
"""오케스트레이터·엔드포인트가 주고받는 입출력. 도메인 공유 계약(A↔B)이 아니라 어시스턴트 로컬."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str
    campaign_id: str | None = None  # 특정 캠페인 맥락(있으면 상세 우선)
    ad_id: str | None = None  # 시뮬 예측 연결 맥락
    thread_id: str | None = None  # 멀티턴 키 — 같은 세션이면 같은 값(없으면 새로 생성)


class Citation(BaseModel):
    kind: str  # "kb"(문서) | "live"(실측 툴)
    source: str  # 문서 파일명 또는 툴 이름
    title: str = ""


class SuggestedAction(BaseModel):
    """행동 의도가 감지됐을 때의 추천 액션 — 어시스턴트는 제안만, 실행은 승인 경로로.

    어시스턴트가 직접 writer/executor를 호출하지 않는다. 이 제안을 받은 화면/오케스트레이터가
    기존 approval→executor 경로(Tier 게이트)로 사람 승인 후 실행한다.
    """

    action_type: str  # PAUSE_CAMPAIGN / ACTIVATE_CAMPAIGN / INCREASE_BUDGET ...
    target_campaign_id: str | None = None
    tier: str  # TIER_1 / TIER_3 ...
    requires_approval: bool  # Tier가 자동승인 한도(Tier1) 초과면 True(사람 승인 필요)
    rationale: str


class AskResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)  # 답에 쓰인 실측 수치(디버그·검증용)
    suggested_action: SuggestedAction | None = None  # 행동 의도 시 추천(실행은 승인 경로)
    requires_approval: bool = False  # write 제안이 사람 승인 게이트에서 멈췄는가(HITL)
    thread_id: str | None = None  # interrupt로 멈춘 그래프의 재개 키(승인 경로에서 사용)
