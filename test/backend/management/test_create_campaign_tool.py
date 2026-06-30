# create_campaign 툴 결과가 meta.widget(3k 통로)로 합성되는지 — 오케스트레이터 순수 변환만 검증.
from langchain_core.messages import AIMessage

from api.assistant.deep_agent import _state_to_result


def test_state_to_result_carries_create_prefill():
    state = {
        "messages": [
            AIMessage(content="새 캠페인 생성 폼을 준비했어요. 값을 확인하고 승인해 주세요.")
        ],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "create_prefill": {"objective": "leads", "total_budget_krw": 50000},
    }
    result = _state_to_result(state)
    assert result.meta["widget"] == {
        "type": "create_campaign",
        "data": {"prefill": {"objective": "leads", "total_budget_krw": 50000}},
    }


def test_state_to_result_no_prefill_has_no_widget():
    state = {
        "messages": [AIMessage(content="일반 답변")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "create_prefill": None,
    }
    result = _state_to_result(state)
    assert "widget" not in result.meta


def test_state_to_result_create_prefill_forces_deep_agent_source():
    # 멀티툴 턴 — management 결과가 sub_results에 있어도 create 신호가 source를 deep-agent로 고정해
    # chat.py의 management 게이트가 잘못 발동하지 않게 한다.
    state = {
        "messages": [AIMessage(content="새 캠페인 생성 폼을 준비했어요.")],
        "sub_results": {"management": {"source": "management", "suggested_action": {"x": 1}}},
        "requires_approval": False,
        "thread_id": None,
        "create_prefill": {"objective": "leads"},
    }
    result = _state_to_result(state)
    assert result.meta["source"] == "deep-agent"
    assert result.meta["widget"]["type"] == "create_campaign"
