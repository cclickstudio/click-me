# 섹션 기반 ChatCard 계약 — discriminated union·기본값·trace allowlist·actions 미직렬화
import pytest
from pydantic import ValidationError

from domain.management.assistant.chat_cards import (
    TRACE_RAW_ALLOWLIST,
    ChatCard,
    MetricItem,
    MetricsSection,
    SummarySection,
    TraceInfo,
    filtered_trace_raw,
)


def test_chatcard_defaults():
    card = ChatCard(sections=[SummarySection(text="요약")])
    assert card.version == 1
    assert card.type == "management"
    assert card.status is None
    assert card.badges == []


def test_section_discriminated_by_kind():
    card = ChatCard(
        sections=[
            SummarySection(text="결론"),
            MetricsSection(items=[MetricItem(label="이번 달 소진", value="29,082원")]),
        ]
    )
    dumped = card.model_dump(mode="json")
    assert dumped["sections"][0]["kind"] == "summary"
    assert dumped["sections"][1]["kind"] == "metrics"
    assert dumped["sections"][1]["items"][0]["value"] == "29,082원"


def test_section_round_trips_by_kind():
    card = ChatCard.model_validate({"sections": [{"kind": "summary", "text": "x"}]})
    assert isinstance(card.sections[0], SummarySection)


def test_unknown_section_kind_rejected():
    with pytest.raises(ValidationError):
        ChatCard.model_validate({"sections": [{"kind": "nope", "text": "x"}]})


def test_actions_not_serialized():
    card = ChatCard(sections=[SummarySection(text="x")])
    assert "actions" not in card.model_dump(mode="json")


def test_filtered_trace_raw_drops_non_allowlist():
    raw = {"turn_id": "t1", "period": "2026-06", "account_token": "SECRET", "rows": [1, 2, 3]}
    out = filtered_trace_raw(raw)
    assert out == {"turn_id": "t1", "period": "2026-06"}
    assert "account_token" not in TRACE_RAW_ALLOWLIST


def test_trace_info_turn_id_only():
    t = TraceInfo(turn_id="mgmt-s1")
    assert t.turn_id == "mgmt-s1"
    assert t.raw is None
