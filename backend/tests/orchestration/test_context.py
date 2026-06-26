# TurnContext 블랙보드 — step.id로 저장, output_of(action)는 해당 action의 최신 산출 반환
from api.orchestration.context import TurnContext


def test_output_of_returns_none_when_absent():
    assert TurnContext(user_input="q").output_of("generate") is None


def test_output_of_returns_latest_for_action():
    ctx = TurnContext(user_input="q")
    ctx.results["generate-1"] = {"ad_id": "a1"}
    ctx.results["generate-2"] = {"ad_id": "a2"}
    assert ctx.output_of("generate") == {"ad_id": "a2"}


def test_output_of_isolates_by_action():
    ctx = TurnContext(user_input="q")
    ctx.results["generate-1"] = {"x": 1}
    ctx.results["simulate-1"] = {"y": 2}
    assert ctx.output_of("simulate") == {"y": 2}
    assert ctx.output_of("generate") == {"x": 1}


def test_output_of_handles_gaps_and_returns_max_n():
    # replan으로 번호가 비어도 최대 n(최신)을 반환
    ctx = TurnContext(user_input="q")
    ctx.results["generate-1"] = {"v": 1}
    ctx.results["generate-3"] = {"v": 3}
    assert ctx.output_of("generate") == {"v": 3}


def test_output_of_ignores_malformed_keys():
    ctx = TurnContext(user_input="q")
    ctx.results["generate-1"] = {"v": 1}
    ctx.results["generate-x"] = {"bad": True}  # 숫자 아님 → 무시
    ctx.results["weird"] = {"bad": True}  # 구분자 없음 → 무시
    assert ctx.output_of("generate") == {"v": 1}


def test_defaults_are_independent_per_instance():
    a = TurnContext(user_input="a")
    b = TurnContext(user_input="b")
    a.results["generate-1"] = {"x": 1}
    assert b.results == {}  # 기본 dict가 인스턴스 간 공유되지 않음
