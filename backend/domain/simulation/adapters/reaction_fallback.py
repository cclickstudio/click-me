# 반응 엔진 폴백 래퍼(프로바이더 무관) — primary 실패 시 다음 엔진으로. 503 벤더 리스크 완충.
from __future__ import annotations

import logging

from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction

logger = logging.getLogger("clickme")


class FallbackReactionEngine:
    """반응 엔진 체인 — 앞 엔진이 실패(재시도 소진 포함)하면 다음 엔진으로 폴백한다.

    각 엔진은 자체 백오프 재시도를 갖고, 그걸 다 쓰고도 예외면 비로소 다음으로 넘어간다.
    react 인터페이스(덕타이핑)만 맞으면 어떤 프로바이더든 체인에 넣을 수 있다.
    """

    def __init__(self, engines) -> None:
        if not engines:
            raise ValueError("FallbackReactionEngine에 최소 1개 엔진이 필요하다")
        self._engines = list(engines)
        self.version = "+".join(getattr(e, "version", "?") for e in self._engines)

    async def react(self, persona, ad: AdInterpretation) -> PersonaReaction:
        last_exc: Exception | None = None
        for i, engine in enumerate(self._engines):
            try:
                return await engine.react(persona, ad)
            except Exception as exc:  # 한 엔진 실패 → 다음 폴백(둘 다 실패하면 마지막 예외 전파)
                last_exc = exc
                logger.warning(
                    "반응 엔진[%d/%d] 실패, 폴백 시도: %s",
                    i + 1,
                    len(self._engines),
                    exc,
                )
        raise last_exc  # type: ignore[misc]
