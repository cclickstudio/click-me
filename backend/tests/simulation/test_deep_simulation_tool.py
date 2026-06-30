# run_simulation·ask_simulation 툴 결과가 deep_agent _state_to_result로 합성되는지 검증(순수 변환).
from langchain_core.messages import AIMessage

from api.assistant.deep_agent import _state_to_result


def test_state_to_result_carries_sim_form():
    # run_simulation 신호 → sim_form 위젯으로 합성 + source="simulation" 고정.
    state = {
        "messages": [AIMessage(content="시뮬레이션 입력 폼을 준비했어요.")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "sim_form": {"ad_title": "바나나우유", "ad_content": "시원한 한 모금"},
    }
    result = _state_to_result(state)
    assert result.meta["widget"] == {
        "type": "sim_form",
        "data": {"ad_title": "바나나우유", "ad_content": "시원한 한 모금"},
    }
    assert result.meta["source"] == "simulation"


def test_state_to_result_no_sim_form_has_no_widget():
    state = {
        "messages": [AIMessage(content="일반 답변")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "sim_form": None,
    }
    result = _state_to_result(state)
    assert "widget" not in result.meta


def test_state_to_result_ask_simulation_reflected():
    # ask_simulation sub_result → source·used_tools에 반영(조회·해석 경로).
    state = {
        "messages": [AIMessage(content="구매의도는 평균 3.4점입니다.")],
        "sub_results": {
            "simulation": {"source": "simulation", "citations": [], "used_tools": []}
        },
        "requires_approval": False,
        "thread_id": None,
        "sim_form": None,
    }
    result = _state_to_result(state)
    assert result.meta["source"] == "simulation"
    assert "ask_simulation" in result.meta["used_tools"]
    assert "widget" not in result.meta
