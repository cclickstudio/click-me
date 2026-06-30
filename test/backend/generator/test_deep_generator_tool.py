# run_generator 신호 결과가 deep_agent _state_to_result로 gen_form 위젯으로 합성되는지 검증(순수 변환).
from langchain_core.messages import AIMessage

from api.assistant.deep_agent import _state_to_result


def test_state_to_result_carries_gen_form():
    # run_generator 신호 → gen_form 위젯으로 합성 + source="generator" 고정.
    state = {
        "messages": [AIMessage(content="생성 입력 폼을 준비했어요.")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "gen_form": {"product_name": "수분크림", "campaign_objective": "conversion"},
    }
    result = _state_to_result(state)
    assert result.meta["widget"] == {
        "type": "gen_form",
        "data": {"product_name": "수분크림", "campaign_objective": "conversion"},
    }
    assert result.meta["source"] == "generator"


def test_state_to_result_no_gen_form_has_no_widget():
    state = {
        "messages": [AIMessage(content="카피 전략은 이렇습니다.")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "gen_form": None,
    }
    result = _state_to_result(state)
    assert "widget" not in result.meta
