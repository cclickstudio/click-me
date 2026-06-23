# 어시스턴트 서브에이전트 공통 계약 — 오케스트레이터가 도메인 서브에이전트를 동일 인터페이스로 호출
"""팀 합의(공통 계약 준수)용. 시뮬·생성 서브에이전트가 이 입출력을 따른다.

context_id는 도메인 맥락 식별자(시뮬=simulation_id, 생성=generation_id)로 도메인이 해석한다.
매니지는 독립 개발 상태라 자체 계약(AskRequest/AskResult)을 유지하고, 오케스트레이터가 흡수한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantRequest(BaseModel):
    question: str
    context_id: str | None = None  # 도메인 맥락(시뮬=simulation_id, 생성=generation_id)
    ad_id: str | None = None
    project_id: str | None = None  # 목록 조회 스코프(현재 프로젝트)
    history: list[tuple[str, str]] = Field(default_factory=list)  # (role, content) 직전 대화


class Citation(BaseModel):
    kind: str  # "kb"(문서) | "result"(저장된 도메인 결과) | "live"(실측)
    source: str  # 문서 파일명 또는 도구 이름
    title: str = ""


class AssistantResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)  # 답에 쓰인 결과 수치(디버그·검증용)
