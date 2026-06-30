# 생성결과 콜백·개선루프 골든 — [생성결과] 판정 + 재시뮬 approval/완료 분기
"""result_callback이 loop_state를 보고 재시뮬 approval 또는 완료 안내를 정확히 만드는지 고정한다."""

from domain.chat import result_callback
from domain.chat.loop_state import MAX_LOOP, get_loop_state, reset_loop_state


def test_is_result_callback():
    assert result_callback.is_result_callback("[생성결과] 시안 3개 생성됨")
    assert result_callback.is_result_callback("  [생성결과] 공백 앞")
    assert not result_callback.is_result_callback("시뮬레이션 돌려줘")
    assert not result_callback.is_result_callback(None)


def test_offers_rerun_within_budget():
    sid = "s-cb-rerun"
    reset_loop_state(sid)
    loop = get_loop_state(sid)
    loop.weak_reasons = ["거부율 높음", "구매의도 낮음"]
    _answer, meta = result_callback.handle(sid)
    assert meta["source"] == "generator"
    assert meta["approval"]["action"] == "rerun_simulation"
    assert meta["approval"]["reasons"] == ["거부율 높음", "구매의도 낮음"]
    assert "loop_done" not in meta
    # phase가 gen_done으로 전이
    assert get_loop_state(sid).phase == "gen_done"
    reset_loop_state(sid)


def test_done_at_max_loop():
    sid = "s-cb-done"
    reset_loop_state(sid)
    loop = get_loop_state(sid)
    loop.loop_count = MAX_LOOP
    _answer, meta = result_callback.handle(sid)
    assert meta.get("loop_done") is True
    assert "approval" not in meta
    reset_loop_state(sid)
