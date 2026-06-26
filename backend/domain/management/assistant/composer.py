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
    DiagnosisSection,
    EmptyStateSection,
    EvidenceSection,
    MetricItem,
    MetricsSection,
    ProposalSection,
    ReviewSection,
    SummarySection,
    TraceInfo,
)

if TYPE_CHECKING:
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


def _strip_directive_sentences(line: str) -> str:
    # 한 줄 안에서 실행 지시 문장만 제거(줄 자체 구조는 보존).
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", line.strip()) if s]
    kept = [s for s in sentences if not any(m in s for m in _DIRECTIVE_MARKERS)]
    return " ".join(kept)


def _descriptive_conclusion(answer: str) -> str:
    # 지시문은 제거하되 줄바꿈·목록 구조는 보존(프론트 마크다운 렌더 대비). 빈 줄 3+는 2로 정리.
    lines = [_strip_directive_sentences(ln) for ln in answer.strip().split("\n")]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned or _NEUTRAL_CONCLUSION


def _won(value: float) -> str:
    return f"{round(value):,}원"


def _metrics_section(evidence: dict) -> MetricsSection | None:
    items = [
        MetricItem(label=label, value=_won(evidence[key]))
        for key, label in _METRIC_LABELS
        if isinstance(evidence.get(key), (int, float)) and not isinstance(evidence.get(key), bool)
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


def derive_severity(diagnostic) -> str:
    """진단만으로 severity 파생(tier 미사용). 계약상 info 없음 → neutral."""
    if diagnostic is None or diagnostic.diagnostic_status != "ok" or not diagnostic.anomaly:
        return "neutral"
    dx = diagnostic.diagnosis  # DiagnosisView
    if dx is not None and dx.status == "confirmed":
        return "critical" if dx.confidence >= 0.8 else "warning"
    return "neutral"


def _diagnosis_section(dx) -> DiagnosisSection:  # dx: DiagnosisView
    return DiagnosisSection(
        title="진단",
        anomaly_type=dx.anomaly_type,
        status=dx.status,
        confidence=dx.confidence,
        hypothesis=dx.hypothesis,
    )


def _proposal_preview_section(pv) -> ProposalSection:  # pv: ProposalPreview
    return ProposalSection(
        title="제안(미리보기)",
        action_type=pv.action_type,
        rationale=pv.hypothesis or None,
        preview_id=pv.preview_id,
        campaign_id=pv.campaign_id,
        tier=pv.tier,
        budget_before_krw=pv.budget_before_krw,
        budget_after_krw=pv.budget_after_krw,
        executable=False,
    )


def compose_card(res: AskResult, *, turn_id: str) -> ChatCard:
    sections: list = [SummarySection(title="결론", text=_descriptive_conclusion(res.answer))]
    metrics = _metrics_section(res.evidence or {})
    if metrics is not None:
        sections.append(metrics)

    diag = res.diagnostic
    status = derive_severity(diag)

    if diag is not None and diag.diagnostic_status in ("unavailable", "failed"):
        # 진단 불가/실패 — composer 결정적(empty_state + neutral). LLM 미경유.
        sections.append(
            EmptyStateSection(title="진단", text=diag.reason or "진단 데이터를 가져올 수 없어요.")
        )
        return ChatCard(
            type="management",
            status="neutral",
            badges=[],
            sections=sections,
            trace=TraceInfo(turn_id=turn_id),
        )

    if (
        diag is not None
        and diag.diagnostic_status == "ok"
        and diag.anomaly
        and diag.diagnosis is not None
    ):
        sections.append(_diagnosis_section(diag.diagnosis))
        if diag.proposal_preview is not None:
            sections.append(_proposal_preview_section(diag.proposal_preview))
        badges = [Badge(label=diag.diagnosis.anomaly_type, tone="warning")]
        return ChatCard(
            type="management",
            status=status,
            badges=badges,
            sections=sections,
            trace=TraceInfo(turn_id=turn_id),
        )

    # diag None(일반 질문) 또는 ok+no-anomaly → 기존 v0 경로(suggested_action/evidence)
    sa = res.suggested_action
    if sa is not None:
        sections.append(_proposal_section(sa))
        sections.append(_review_section(sa))
    evidence = _evidence_section(res)
    if evidence is not None:
        sections.append(evidence)
    return ChatCard(
        type="management",
        status=(status if diag is not None else None),
        badges=_badges(sa),
        sections=sections,
        trace=TraceInfo(turn_id=turn_id),
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
