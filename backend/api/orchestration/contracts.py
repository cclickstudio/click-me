# 오케스트레이터 ↔ 도메인 경계 계약 — 도메인 내부를 import하지 않는다(의존성 역전)
from __future__ import annotations

from typing import Any, Protocol


class DomainAgent(Protocol):
    domain: str

    async def ask(self, req: Any) -> Any: ...
