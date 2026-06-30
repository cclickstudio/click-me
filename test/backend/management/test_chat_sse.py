# stream_turn SSE 스트리밍 테스트 — 이벤트 시퀀스·final status·결론 재조합
import json

import pytest

from domain.management.assistant.chat_cards import CardStatus
from domain.management.assistant.composer import compose_turn, stream_turn
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _parse(lines: list[str]) -> list[dict]:
    out = []
    for ln in lines:
        assert ln.startswith("data: "), f"expected 'data: ' prefix, got: {ln!r}"
        assert ln.endswith("\n\n"), f"expected trailing blank line, got: {ln!r}"
        out.append(json.loads(ln[len("data: ") :].strip()))
    return out


async def _collect(env: object) -> list[dict]:
    return _parse([chunk async for chunk in stream_turn(env)])


@pytest.mark.asyncio
async def test_event_sequence_conclusion_then_cards_then_final():
    res = AskResult(
        answer="일시중지를 제안합니다.",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=SuggestedAction(
            action_type="PAUSE_CAMPAIGN",
            tier="TIER_1",
            requires_approval=False,
            rationale="r",
        ),
    )
    env = compose_turn(res, turn_id="t1")
    events = await _collect(env)
    names = [e["event"] for e in events]
    assert names[0] == "conclusion_delta"
    assert names[-1] == "final"
    card_events = [e for e in events if e["event"] == "card_ready"]
    assert card_events[-1]["card"]["kind"] == "actionbar"


@pytest.mark.asyncio
async def test_final_status_ok_when_all_cards_ok():
    res = AskResult(answer="정상입니다.", citations=[Citation(kind="live", source="live_budget")])
    env = compose_turn(res, turn_id="t2")
    events = await _collect(env)
    final = events[-1]
    assert final["event"] == "final"
    assert final["turn_id"] == "t2"
    assert final["status"] == "ok"


@pytest.mark.asyncio
async def test_final_status_partial_when_a_card_degraded():
    res = AskResult(answer="x", citations=[Citation(kind="live", source="live_budget")])
    env = compose_turn(res, turn_id="t3")
    env.cards[0].status = CardStatus.DEGRADED
    events = await _collect(env)
    assert events[-1]["status"] == "partial"


@pytest.mark.asyncio
async def test_conclusion_streamed_in_chunks_reassembles():
    res = AskResult(answer="a" * 60)  # 지시 마커 없음 → 서술 가드 통과, 원문 보존
    env = compose_turn(res, turn_id="t4")
    events = await _collect(env)
    text = "".join(e["text"] for e in events if e["event"] == "conclusion_delta")
    assert text == "a" * 60


@pytest.mark.asyncio
async def test_final_status_ok_with_no_cards():
    # 카드 0개(인용·제안 모두 없음) read-only 턴도 final은 ok.
    res = AskResult(answer="정상입니다.")
    env = compose_turn(res, turn_id="t5")
    assert env.cards == []
    events = await _collect(env)
    assert events[-1]["event"] == "final"
    assert events[-1]["status"] == "ok"
