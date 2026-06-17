# 선발 재랭킹 LLM 어댑터 — 스칼라 동점 후보를 텍스트(실제 발언·사유·감정)로 가른다.
#
# selector의 RerankFn 계약(역할, 역할정의, 동점후보) → persona_id 을 구현. N표 다수결로 변동성 제거.
# 명확한 단독 승자일 때만 id를 반환하고, 전부 실패하거나 표가 갈리면 "" → selector가 결정론 폴백.
# 엔진 라우팅·JSON 파싱은 llm_debate._Clients 재사용(같은 adapters 패키지). 기본 Sonnet(판단 신뢰).
from __future__ import annotations

import logging
from collections import Counter

from domain.simulation.adapters.llm_debate import _Clients
from domain.simulation.contracts.schemas import PersonaReaction

logger = logging.getLogger("clickme")

_SELECTOR_SYS = (
    "당신은 광고 소비자 토론 패널을 선발하는 분석가입니다. "
    "주어진 역할 정의에 가장 부합하는 후보 1명을 고르세요. 반드시 JSON만 출력."
)


def _candidate_block(cands: list[PersonaReaction]) -> str:
    """후보들의 질적 신호를 LLM 판단용 텍스트로 — 스칼라가 못 가른 결을 발언·사유로 드러낸다."""
    lines: list[str] = []
    for i, r in enumerate(cands):
        acted = "행동함(클릭/구매)" if r.aisas.action else "행동 안 함"
        rej = "광고 거부함" if r.rejected else "거부 안 함"
        parts = [
            f"[{i + 1}] id={r.persona_id}",
            f"  신뢰 {r.trust}/5, 구매의도 {r.purchase_intent}/5, {acted}, {rej}",
            f"  감정: {r.emotion_tag}",
        ]
        if r.utterance:
            parts.append(f'  실제 발언: "{r.utterance}"')
        if r.perceived_message:
            parts.append(f"  받아들인 메시지: {r.perceived_message}")
        if r.drop_reason_tag:
            parts.append(f"  이탈 사유: {r.drop_reason_tag}")
        if r.rejection_reason_tag:
            parts.append(f"  거부 사유: {r.rejection_reason_tag}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


class LLMSelector:
    """동점 후보 재랭킹 — votes표 다수결. 단독 승자만 채택, 애매하면 결정론에 맡긴다(빈 문자열)."""

    def __init__(
        self, clients: _Clients | None = None, *, engine: str = "sonnet", votes: int = 3
    ) -> None:
        self._c = clients or _Clients()
        self._engine = engine
        self._votes = votes

    def choose(self, role: str, role_def: str, candidates: list[PersonaReaction]) -> str:
        """역할 정의에 가장 부합하는 후보 id. 단독 다수결 승자만 반환, 그 외 ""(결정론 폴백)."""
        ids = [r.persona_id for r in candidates]
        user = (
            f"역할: {role}\n역할 정의: {role_def}\n\n"
            f"후보:\n{_candidate_block(candidates)}\n\n"
            "수치(신뢰·구매의도)는 후보들이 거의 같다 — 발언과 사유의 뉘앙스로 판단하라.\n"
            f"역할 정의에 가장 부합하는 후보의 id 하나를 고르세요(반드시 다음 중: {ids}).\n"
            '아래 JSON으로만: {"pick":"<id>","reason":"한 줄 근거"}'
        )
        votes: list[str] = []
        for _ in range(self._votes):
            try:
                data = self._c.complete_json(self._engine, _SELECTOR_SYS, user, max_tokens=300)
                pid = str(data.get("pick", "")).strip()
                if pid in ids:
                    votes.append(pid)
            except Exception as exc:  # noqa: BLE001
                logger.warning("선발 재랭킹 호출 실패 role=%s err=%s", role, exc)
        if not votes:
            return ""  # 전부 실패 → selector가 결정론 폴백
        counts = Counter(votes)
        top = max(counts.values())
        winners = [k for k, v in counts.items() if v == top]
        return winners[0] if len(winners) == 1 else ""  # 표 갈리면 결정론에 맡김
