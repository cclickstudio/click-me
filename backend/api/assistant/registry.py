# 서브에이전트 레지스트리 — 의도(Intent) → 핸들러 매핑(plug-in 지점)
"""오케스트레이터의 디스패치 테이블. wiring(composition root)에서 도메인 핸들러를 등록한다.

핸들러 시그니처: async (SubagentRequest) -> SubagentResult.
이 한 곳만 보면 어떤 의도가 어떤 도메인으로 가는지 알 수 있다(예측가능 — G5).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from api.assistant.contracts import Intent, SubagentRequest, SubagentResult

Handler = Callable[[SubagentRequest], Awaitable[SubagentResult]]


class SubagentRegistry:
    def __init__(self) -> None:
        self._handlers: dict[Intent, Handler] = {}

    def register(self, intent: Intent, handler: Handler) -> None:
        self._handlers[intent] = handler

    def get(self, intent: Intent) -> Handler | None:
        return self._handlers.get(intent)

    def has(self, intent: Intent) -> bool:
        return intent in self._handlers

    @property
    def intents(self) -> list[Intent]:
        return list(self._handlers)
