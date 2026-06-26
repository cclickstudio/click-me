# 챗 숏텀 메모리(state 기반) — 계약·리듀서·헬퍼·delegate·어댑터 프리앰블 검증.


def test_subagent_request_history_defaults_empty():
    from domain.chat.contracts.agent_io import SubAgentRequest

    req = SubAgentRequest(question="hi")
    assert req.history == []
    req2 = SubAgentRequest(question="hi", history=[{"role": "user", "content": "x"}])
    assert req2.history[0]["content"] == "x"
