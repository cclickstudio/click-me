# 오케스트레이션 턴 블랙보드 — 스텝 산출을 step.id로 누적, output_of로 역할(action) 최신 조회
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnContext:
    user_input: str
    session_id: str = ""
    ad_id: str | None = None
    attachments: tuple[Any, ...] = ()  # 자리만 — S3 멀티모달에서 채움
    results: dict[str, Any] = field(default_factory=dict)  # step.id -> output (점진 누적)

    def output_of(self, action: str) -> Any | None:
        # 저장은 고유 step.id({action}-{n}), 접근은 의미역 — 해당 action의 최신(n 최대) 산출.
        matched = [
            (int(suffix), value)
            for key, value in self.results.items()
            if "-" in key
            for head, _, suffix in [key.rpartition("-")]
            if head == action and suffix.isdigit()
        ]
        if not matched:
            return None
        return max(matched, key=lambda pair: pair[0])[1]
