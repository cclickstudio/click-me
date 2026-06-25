# stream_card SSE 시퀀스 + 주입형 _management_card_stream(앱·DB 없이)
import json

import pytest

from domain.management.assistant.composer import compose_card, stream_card
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _parse(lines: list[str]) -> list[dict]:
    out = []
    for ln in lines:
        assert ln.startswith("data: ") and ln.endswith("\n\n")
        out.append(json.loads(ln[len("data: ") :].strip()))
    return out


async def _collect_stream(card) -> list[dict]:
    return _parse([chunk async for chunk in stream_card(card)])


@pytest.mark.asyncio
async def test_sequence_summary_then_card_then_final():
    res = AskResult(
        answer="일시중지를 제안합니다.",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=SuggestedAction(
            action_type="PAUSE_CAMPAIGN",
            target_campaign_id="camp_1",
            tier="TIER_1",
            requires_approval=False,
            rationale="r",
        ),
    )
    card = compose_card(res, turn_id="t1")
    events = await _collect_stream(card)
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "summary_delta"
    assert "card" in kinds
    assert kinds[-1] == "final"
    assert events[-1]["status"] == "ok"
    assert events[-1]["turn_id"] == "t1"


@pytest.mark.asyncio
async def test_summary_delta_reassembles():
    card = compose_card(AskResult(answer="a" * 60), turn_id="t2")  # 지시 마커 없음 → 원문 보존
    events = await _collect_stream(card)
    text = "".join(e["text"] for e in events if e["kind"] == "summary_delta")
    assert text == "a" * 60


@pytest.mark.asyncio
async def test_card_event_carries_sections():
    card = compose_card(
        AskResult(answer="정상입니다.", evidence={"this_month_spent_krw": 100}), turn_id="t3"
    )
    events = await _collect_stream(card)
    card_event = next(e for e in events if e["kind"] == "card")
    assert [s["kind"] for s in card_event["payload"]["sections"]] == ["summary", "metrics"]


@pytest.mark.asyncio
async def test_management_card_stream_happy_path():
    from api.routers.chat import _management_card_stream

    async def fake_assistant(req):
        assert req.question == "예산?"
        return AskResult(
            answer="예산은 정상입니다.", citations=[Citation(kind="live", source="live_budget")]
        )

    recorded = []

    async def fake_record(**kw):
        recorded.append(kw)

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?",
            session_id="s1",
            ad_id=None,
            assistant=fake_assistant,
            record=fake_record,
        )
    ]
    events = _parse(chunks)
    assert events[0]["kind"] == "summary_delta"
    assert events[-1]["kind"] == "final" and events[-1]["status"] == "ok"
    assert recorded and recorded[0]["thread_id"] == "mgmt-s1"


@pytest.mark.asyncio
async def test_management_card_stream_failure_emits_safe_error_then_final_failed():
    from api.routers.chat import _management_card_stream

    async def boom(req):
        raise RuntimeError("assistant down: SECRET_TOKEN=abc")

    async def fake_record(**kw):
        pass

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?", session_id="s1", ad_id=None, assistant=boom, record=fake_record
        )
    ]
    events = _parse(chunks)
    err = next(e for e in events if e["kind"] == "error")
    assert err["scope"] == "turn"
    assert "SECRET_TOKEN" not in err["message"]  # raw exception 미노출
    assert events[-1]["kind"] == "final" and events[-1]["status"] == "failed"


@pytest.mark.asyncio
async def test_management_card_stream_record_failure_is_best_effort():
    from api.routers.chat import _management_card_stream

    async def fake_assistant(req):
        return AskResult(answer="예산은 정상입니다.")

    async def boom_record(**kw):
        raise RuntimeError("db down")

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?",
            session_id="s1",
            ad_id=None,
            assistant=fake_assistant,
            record=boom_record,
        )
    ]
    events = _parse(chunks)
    assert events[-1]["kind"] == "final" and events[-1]["status"] == "ok"
    assert not any(e["kind"] == "error" for e in events)
