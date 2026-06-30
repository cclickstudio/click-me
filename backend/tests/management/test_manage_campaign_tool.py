# manage_campaign 툴 결과가 meta.widget(type='campaign_action') + action 페이로드로 합성되는지.
from langchain_core.messages import AIMessage

from api.assistant.deep_agent import _state_to_result


def _state(action):
    return {
        "messages": [AIMessage(content="요청을 확인했어요.")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "create_prefill": None,
        "campaign_action": action,
    }


def test_state_to_result_carries_campaign_action():
    result = _state_to_result(
        _state({"action": "pause", "campaign_id": "c_1", "campaign_name": "가을세일"})
    )
    assert result.meta["widget"] == {
        "type": "campaign_action",
        "data": {
            "action": {
                "action": "pause",
                "campaign_id": "c_1",
                "campaign_name": "가을세일",
            }
        },
    }
    assert result.meta["source"] == "deep-agent"  # management 게이트 오발동 방지


def test_state_to_result_no_action_has_no_widget():
    result = _state_to_result(_state(None))
    assert "widget" not in result.meta
