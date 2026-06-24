# (kind, type, version) 레지스트리 — 프론트 렌더러와 Composer가 공유하는 A↔B 계약의 단일 출처.
from __future__ import annotations

from .models import Card, CardKind

# (kind, type) -> 지원 version 집합. B 단계에서 result에 kpi_distribution/variants 등 추가.
_REGISTRY: dict[tuple[CardKind, str], set[int]] = {
    (CardKind.EVIDENCE, "rag_citations"): {1},
    (CardKind.RESULT, "action_proposal"): {1},
    (CardKind.REVIEW, "policy_check"): {1},
    (CardKind.ACTIONBAR, "actions"): {1},
}


def is_registered(kind: CardKind, type_: str, version: int) -> bool:
    return version in _REGISTRY.get((kind, type_), set())


def validate_card(card: Card) -> None:
    if not is_registered(card.kind, card.payload.type, card.payload.version):
        raise ValueError(
            f"unregistered card: ({card.kind}, {card.payload.type}, v{card.payload.version})"
        )
