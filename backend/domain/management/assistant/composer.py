# Composer — AskResult를 도메인 비종속 ChatCard(섹션)로 normalize한다. 서술 가드는 여기서 강제.
from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from .chat_cards import (
    Badge,
    ChatCard,
    Citation,
    EvidenceSection,
    MetricItem,
    MetricsSection,
    ProposalSection,
    ReviewSection,
    SummarySection,
    TraceInfo,
)

if TYPE_CHECKING:
    from .chat_cards import CardSection
    from .contracts import AskResult, SuggestedAction

# 결론에서 제거할 실행 지시 마커. 행동 가능한 주장은 카드(proposal)로.
_DIRECTIVE_MARKERS = (
    "실행하세요",
    "실행하면 됩니다",
    "지금 실행",
    "바로 실행",
    "바로 적용",
    "집행하세요",
    "눌러서 실행",
)
_NEUTRAL_CONCLUSION = "자세한 내용은 아래 카드를 확인하세요."

# evidence dict 숫자 → 표시 라벨(KRW). 없는 키는 건너뛴다.
_METRIC_LABELS: tuple[tuple[str, str], ...] = (
    ("this_month_spent_krw", "이번 달 소진"),
    ("runrate_projection_krw", "월말 예상"),
    ("account_balance_krw", "계정 잔액"),
)


def _descriptive_conclusion(answer: str) -> str:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s]
    kept = [s for s in sentences if not any(m in s for m in _DIRECTIVE_MARKERS)]
    return " ".join(kept).strip() or _NEUTRAL_CONCLUSION


def _won(value: object) -> str:
    return f"{int(value):,}원"


def _metrics_section(evidence: dict) -> MetricsSection | None:
    items = [
        MetricItem(label=label, value=_won(evidence[key]))
        for key, label in _METRIC_LABELS
        if isinstance(evidence.get(key), (int, float))
    ]
    if not items:
        return None
    period = evidence.get("period")
    return MetricsSection(title=f"핵심 지표 ({period})" if period else "핵심 지표", items=items)


def _proposal_section(sa: SuggestedAction) -> ProposalSection:
    return ProposalSection(title="제안", action_type=sa.action_type, rationale=sa.rationale)


def _review_section(sa: SuggestedAction) -> ReviewSection:
    decision = "needs_approval" if sa.requires_approval else "auto_ok"
    return ReviewSection(title="검수", decision=decision, rationale=sa.rationale)


def _evidence_section(res: AskResult) -> EvidenceSection | None:
    if not res.citations and not res.used_tools:
        return None
    return EvidenceSection(
        title="근거",
        citations=[Citation(kind=c.kind, source=c.source, title=c.title) for c in res.citations],
        used_tools=list(res.used_tools),
    )


def _badges(sa: SuggestedAction | None) -> list[Badge]:
    if sa is None:
        return []
    decision = "needs_approval" if sa.requires_approval else "auto_ok"
    return [
        Badge(label=sa.tier, tone="neutral"),
        Badge(label="draft", tone="muted"),
        Badge(label=decision, tone="success" if decision == "auto_ok" else "warning"),
    ]


def compose_card(res: AskResult, *, turn_id: str) -> ChatCard:
    """AskResult를 ChatCard로. 섹션 순서 summary→metrics→proposal→review→evidence, 없으면 생략."""
    sections: list[CardSection] = [
        SummarySection(title="결론", text=_descriptive_conclusion(res.answer))
    ]

    metrics = _metrics_section(res.evidence or {})
    if metrics is not None:
        sections.append(metrics)

    sa = res.suggested_action
    if sa is not None:
        sections.append(_proposal_section(sa))
        sections.append(_review_section(sa))

    evidence = _evidence_section(res)
    if evidence is not None:
        sections.append(evidence)

    return ChatCard(
        type="management",
        badges=_badges(sa),
        sections=sections,
        trace=TraceInfo(turn_id=turn_id),  # v0 — raw 미전송
    )


# SSE 한 줄 직렬화 — 와이어 포맷 단일 출처(라우터 오류 경로도 재사용).
def format_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunks(text: str, size: int = 24) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _summary_text(card: ChatCard) -> str:
    for section in card.sections:
        if section.kind == "summary":
            return section.text
    return ""


async def stream_card(card: ChatCard) -> AsyncGenerator[str, None]:
    """ChatCard를 2단계 SSE로 — summary 텍스트 스트리밍 → card → final(항상)."""
    for piece in _chunks(_summary_text(card)):
        yield format_sse({"kind": "summary_delta", "text": piece})
    yield format_sse({"kind": "card", "payload": card.model_dump(mode="json")})
    turn_id = card.trace.turn_id if card.trace else None
    yield format_sse({"kind": "final", "turn_id": turn_id, "status": "ok"})
