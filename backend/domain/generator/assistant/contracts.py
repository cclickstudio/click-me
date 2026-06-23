# 광고 생성 어시스턴트 I/O 계약 — 질문/근거+인용 답변
"""오케스트레이터·엔드포인트가 주고받는 입출력. 읽기·해석 전용(생성 실행은 별도 경로)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenAskRequest(BaseModel):
    question: str
    generation_id: str | None = None  # 특정 생성 결과 맥락(있으면 결과 조회 우선)
    ad_id: str | None = None


class Citation(BaseModel):
    kind: str  # "kb"(문서) | "result"(저장된 생성 결과)
    source: str  # 문서 파일명 또는 도구 이름
    title: str = ""


class GenAskResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)  # 답에 쓰인 결과 수치(디버그·검증용)
