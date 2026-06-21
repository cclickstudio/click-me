# 챗봇 세션 상태 — 대화 이력 + 누적된 partial_request 보관
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChatSession:
    session_id: str
    messages: list[dict] = field(default_factory=list)
    partial_request: dict = field(default_factory=dict)
    # collecting → confirming → generating
    status: str = "collecting"
    project_id: str | None = None
    generation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
