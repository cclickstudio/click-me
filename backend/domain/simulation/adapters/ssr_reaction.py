# SSR 점수화 반응 어댑터 — 내부 reactor의 서술 텍스트를 임베딩 SSR로 구매의도·신뢰도 분포화
#
# 데코레이터 패턴: react() 시그니처 동일(덕타이핑) — Gemini/GPT 폴백 체인을 그대로 감싼다.
# LLM 정수(purchase_intent·trust)는 SSR 분포 평균(반올림·클램프)으로 덮고, 분포 원본은
# *_dist 필드에 보존(§KPI 분포 표기). SSR 차원 미산출 시 LLM 정수 유지(안전 폴백).
# 앵커 임베딩은 첫 react()에서 1회 lazy 프리컴퓨트(공통부 main.py lifespan 불개입).
from __future__ import annotations

import asyncio

from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction


def build_ssr_input_text(reaction: PersonaReaction) -> str:
    """SSR 입력 텍스트 — reaction_text(자유 서술) 우선, 없으면 utterance 등 기존 필드 폴백.

    구버전 응답(서술 미산출)에도 동작하도록 폴백을 둔다 — 빈 조각은 건너뛴다.
    """
    rt = reaction.reaction_text or {}
    if rt:
        parts = [
            str(rt.get("first_impression") or ""),
            "; ".join(str(t) for t in rt.get("supporting_thoughts") or []),
            "; ".join(str(t) for t in rt.get("opposing_thoughts") or []),
            str(rt.get("final_attitude") or ""),
        ]
    else:
        parts = [
            reaction.utterance or "",
            reaction.perceived_message or "",
            reaction.noticed_first or "",
        ]
    return "\n".join(p for p in parts if p)


def _to_scalar(mean: float) -> int:
    """분포 평균 → 1~5 정수(반올림·클램프) — 기존 int 계약 하위호환용."""
    return max(1, min(5, round(mean)))


class SSRScoringReactor:
    """반응 데코레이터 — 내부 reactor 산출의 구매의도·신뢰도를 SSR(임베딩) 분포로 재산정."""

    def __init__(self, inner, scorer) -> None:
        self._inner = inner
        self._scorer = scorer
        self.version = f"ssr+{getattr(inner, 'version', '?')}"
        self._anchors_ready = False
        self._anchor_lock = asyncio.Lock()

    async def _ensure_anchors(self) -> None:
        if self._anchors_ready:
            return
        async with self._anchor_lock:
            if not self._anchors_ready:
                await self._scorer.precompute_anchors()
                self._anchors_ready = True

    async def react(self, persona, ad: AdInterpretation) -> PersonaReaction:
        reaction = await self._inner.react(persona, ad)
        text = build_ssr_input_text(reaction)
        if not text:
            return reaction  # 점수화할 서술이 없으면 LLM 정수 그대로
        await self._ensure_anchors()
        dists = await self._scorer.score(text)
        update: dict = {}
        if "purchase_intent" in dists:
            update["purchase_intent_dist"] = dists["purchase_intent"]
            update["purchase_intent"] = _to_scalar(dists["purchase_intent"].mean)
        if "trust" in dists:
            update["trust_dist"] = dists["trust"]
            update["trust"] = _to_scalar(dists["trust"].mean)
        return reaction.model_copy(update=update) if update else reaction
