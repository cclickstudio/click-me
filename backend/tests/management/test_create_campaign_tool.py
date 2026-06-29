# create_campaign 툴 결과가 meta.embed/prefill로 합성되는지 — 오케스트레이터 순수 변환만 검증.
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
    assert result.meta["embed"] == "create_campaign"
    assert result.meta["prefill"] == {"objective": "leads", "total_budget_krw": 50000}


def test_state_to_result_no_prefill_has_no_embed():
    state = {
        "messages": [AIMessage(content="일반 답변")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "create_prefill": None,
    }
    result = _state_to_result(state)
    assert "embed" not in result.meta
