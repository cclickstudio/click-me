# Composer — AskResult를 검증된 카드 봉투로 조립한다. 서술 가드·검수 게이트를 여기서 강제.
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .chat_cards import (
    Card,
    CardKind,
    CardPayload,
    TurnEnvelope,
    TurnOrigin,
    validate_card,
)

if TYPE_CHECKING:
    from .contracts import AskResult

# 불변식 ③ — 결론에서 제거할 실행 지시 마커(휴리스틱 1차). 행동 가능한 주장은 카드/액션바로.
_DIRECTIVE_MARKERS = (
    "실행하세요",
    "실행하면 됩니다",
    "지금 실행",
    "바로 실행",
    "바로 적용",
    "집행하세요",
    "눌러서 실행",
)
# 전부 지시문이라 남길 서술이 없을 때의 중립 강등 문구. 원문(지시문) 재노출 금지.
_NEUTRAL_CONCLUSION = "자세한 내용은 아래 카드를 확인하세요."


def _descriptive_conclusion(answer: str) -> str:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s]
    kept = [s for s in sentences if not any(m in s for m in _DIRECTIVE_MARKERS)]
    cleaned = " ".join(kept).strip()
    return cleaned or _NEUTRAL_CONCLUSION  # 전부 지시문이면 중립 강등(원문 재노출 금지)


def _evidence_card(res: AskResult) -> Card | None:
    if not res.citations:
        return None
    return Card(
        kind=CardKind.EVIDENCE,
        payload=CardPayload(
            type="rag_citations",
            version=1,
            data={
                "citations": [
                    {"kind": c.kind, "source": c.source, "title": c.title} for c in res.citations
                ],
                "used_tools": list(res.used_tools),
            },
        ),
    )


def _result_card(res: AskResult) -> Card:
    sa = res.suggested_action
    return Card(
        kind=CardKind.RESULT,
        payload=CardPayload(
            type="action_proposal",
            version=1,
            data={
                "action_type": sa.action_type,
                "target_campaign_id": sa.target_campaign_id,
                "tier": sa.tier,
                "rationale": sa.rationale,
                # MVP — 아직 영속·검증된 proposal이 아님. "바로 실행 가능"으로 오해 금지.
                "stage": "draft",
                "executable": False,
            },
        ),
    )


def _review_card(res: AskResult) -> tuple[Card, str]:
    sa = res.suggested_action
    decision = "needs_approval" if sa.requires_approval else "auto_ok"
    card = Card(
        kind=CardKind.REVIEW,
        payload=CardPayload(
            type="policy_check",
            version=1,
            data={"decision": decision, "tier": sa.tier, "reasons": [sa.rationale]},
        ),
    )
    return card, decision


def _actionbar_card(res: AskResult) -> Card:
    # MVP — 실행 API 미연결이라 변경 액션은 비활성(불변식 ①). proposal_draft로 Plan 2 배선 대비.
    sa = res.suggested_action
    draft = {
        "action_type": sa.action_type,
        "target_campaign_id": sa.target_campaign_id,
        "tier": sa.tier,
    }
    pending = "실행 API 미연결 (Plan 2)"
    actions = [
        {
            "id": "regenerate",
            "label": "다시 생성",
            "kind": "safe",
            "enabled": True,
            "wired": True,
            "proposal_draft": None,
        },
        {
            "id": "approve",
            "label": "승인",
            "kind": "mutating",
            "enabled": False,
            "wired": False,
            "disabled_reason": pending,
            "proposal_draft": draft,
        },
        {
            "id": "execute",
            "label": "실행",
            "kind": "mutating",
            "enabled": False,
            "wired": False,
            "disabled_reason": pending,
            "proposal_draft": draft,
        },
    ]
    return Card(
        kind=CardKind.ACTIONBAR,
        payload=CardPayload(type="actions", version=1, data={"actions": actions}),
    )


def compose_turn(
    res: AskResult, *, turn_id: str, origin: TurnOrigin = TurnOrigin.USER
) -> TurnEnvelope:
    """AskResult를 카드 봉투로 매핑. 슬롯 순서 고정, actionbar는 review 이후 항상 마지막."""
    cards: list[Card] = []

    evidence = _evidence_card(res)
    if evidence is not None:
        cards.append(evidence)

    if res.suggested_action is not None:
        cards.append(_result_card(res))
        review, _decision = _review_card(res)
        cards.append(review)
        cards.append(_actionbar_card(res))  # 항상 마지막

    for card in cards:
        validate_card(card)

    return TurnEnvelope(
        turn_id=turn_id,
        origin=origin,
        conclusion=_descriptive_conclusion(res.answer),
        cards=cards,
    )
