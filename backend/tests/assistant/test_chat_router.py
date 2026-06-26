# 채팅 라우터 — 서브에이전트 결과(ANSWER/ASK/TRIGGER)의 SSE 변환 검증
"""순수 함수 _subagent_sse_events만 검증 — 네트워크·LLM 키 불필요(결정론)."""

import json

from api.routers.chat import _subagent_sse_events
from core.assistant_contracts import Action, StartedEvent, SubagentResult


def _parse(events: list[str]) -> list[dict]:
    """SSE 문자열 리스트 → dict 리스트."""
    out = []
    for e in events:
        assert e.startswith("data: ") and e.endswith("\n\n")
        out.append(json.loads(e[len("data: ") :].strip()))
    return out


def test_answer_emits_meta_then_tokens():
    result = SubagentResult(
        action=Action.ANSWER, message="안녕하세요", meta={"source": "management"}
    )
    objs = _parse(list(_subagent_sse_events(result)))
    assert objs[0] == {"meta": {"source": "management"}}
    assert all("token" in o for o in objs[1:])
    assert "".join(o["token"] for o in objs[1:]) == "안녕하세요"
    assert not any("started" in o for o in objs)


def test_ask_streams_question_tokens_only():
    result = SubagentResult(action=Action.ASK, message="광고 이미지를 넣어주세요")
    objs = _parse(list(_subagent_sse_events(result)))
    assert all("token" in o for o in objs)  # meta 없음 → 토큰만
    assert "".join(o["token"] for o in objs) == "광고 이미지를 넣어주세요"


def test_trigger_emits_started_with_stream_url():
    started = StartedEvent(
        event="generation_started",
        job_id="g1",
        stream_url="/api/generator/generations/g1/stream",
        domain="generator",
    )
    result = SubagentResult(
        action=Action.TRIGGER,
        message="시작했어요",
        meta={"source": "generator"},
        started_event=started,
    )
    objs = _parse(list(_subagent_sse_events(result)))
    assert objs[0] == {"meta": {"source": "generator"}}
    started_objs = [o for o in objs if "started" in o]
    assert len(started_objs) == 1
    assert started_objs[0]["started"]["stream_url"] == "/api/generator/generations/g1/stream"
    assert started_objs[0]["started"]["domain"] == "generator"
