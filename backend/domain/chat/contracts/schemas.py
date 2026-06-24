# 챗 도메인 DTO — 포트 입출력 계약(Pydantic).
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionDTO(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    title: str = "새 채팅"
    summary: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageDTO(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    route: str | None = None
    meta: dict = Field(default_factory=dict)
    created_at: datetime


class MemoryItem(BaseModel):
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    memory_type: str
    content: dict
    salience: float = 0.5
    source_session_id: uuid.UUID | None = None


class MemoryHit(BaseModel):
    id: uuid.UUID
    memory_type: str
    content: dict
    salience: float
    # 점수 [0,1]: top-k는 코사인 유사도(음수 0 클램프), always-load는 1.0 고정.
    # 둘 다 1.0 가능 → score만으로 출처 구분 불가(필요 시 후속 source 필드 검토).
    score: float
