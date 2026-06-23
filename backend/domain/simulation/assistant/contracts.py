# 시뮬레이션 어시스턴트 I/O 계약 — 질문/근거+인용 답변
"""오케스트레이터·엔드포인트가 주고받는 입출력. 매니지와 달리 행동 제안 없음(읽기·해석 전용)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimAskRequest(BaseModel):
    question: str
    simulation_id: str | None = None  # 특정 시뮬 결과 맥락(있으면 결과 조회 우선)
    ad_id: str | None = None


class Citation(BaseModel):
    kind: str  # "kb"(문서) | "result"(저장된 시뮬 결과)
    source: str  # 문서 파일명 또는 도구 이름
    title: str = ""


class SimAskResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)  # 답에 쓰인 결과 수치(디버그·검증용)
