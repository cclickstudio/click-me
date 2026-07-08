# 집행 권장 게이트 — 경계값(클릭≥1% 포함·거부<20% 미만)·settings 폴백
from domain.management.contracts.policy import exec_gate_thresholds, is_executable_verdict


def test_boundary_click_intent_inclusive():
    # 클릭 의향률 1% 정확히는 통과(>=)
    assert is_executable_verdict(0.01, 0.0, min_cir=0.01, max_rej=0.2)
    assert not is_executable_verdict(0.0099, 0.0, min_cir=0.01, max_rej=0.2)


def test_boundary_rejection_exclusive():
    # 거부율 20% 정확히는 실패(<)
    assert is_executable_verdict(0.05, 0.19, min_cir=0.01, max_rej=0.2)
    assert not is_executable_verdict(0.05, 0.2, min_cir=0.01, max_rej=0.2)
    assert not is_executable_verdict(0.01, 0.2, min_cir=0.01, max_rej=0.2)


def test_thresholds_default_fallback():
    class _Empty:
        pass

    assert exec_gate_thresholds(_Empty()) == (0.01, 0.2)


def test_thresholds_read_settings():
    class _S:
        management_exec_gate_min_cir = 0.03
        management_exec_gate_max_rej = 0.15

    assert exec_gate_thresholds(_S()) == (0.03, 0.15)
