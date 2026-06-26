# 챗 숏텀 메모리(state 기반) — 계약·리듀서·헬퍼·delegate·어댑터 프리앰블 검증.


def test_subagent_request_history_defaults_empty():
    from domain.chat.contracts.agent_io import SubAgentRequest

    req = SubAgentRequest(question="hi")
    assert req.history == []
    req2 = SubAgentRequest(question="hi", history=[{"role": "user", "content": "x"}])
    assert req2.history[0]["content"] == "x"


def test_merge_context_keeps_old_overlays_nonnull():
    from domain.chat.graph.state import _merge_context

    out = _merge_context({"ad_id": "a", "x": 1}, {"ad_id": None, "y": 2})
    assert out == {"ad_id": "a", "x": 1, "y": 2}  # 기존 유지 + 새 non-null만 덮어쓰기


def test_merge_context_handles_none_old():
    from domain.chat.graph.state import _merge_context

    assert _merge_context(None, {"a": 1, "b": None}) == {"a": 1}
