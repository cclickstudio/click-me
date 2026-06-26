# 오케스트레이션 정책 상수 — 형태·키 보장(하드코딩 단일 출처)
from api.orchestration import policy


def test_sequential_markers_nonempty():
    assert "그리고" in policy.SEQUENTIAL_MARKERS
    assert len(policy.SEQUENTIAL_MARKERS) >= 3


def test_router_ambiguity_margin_is_float():
    assert isinstance(policy.ROUTER_AMBIGUITY_MARGIN, float)
    assert 0.0 < policy.ROUTER_AMBIGUITY_MARGIN < 1.0


def test_domain_to_action_covers_three_domains():
    assert policy.DOMAIN_TO_ACTION["management"] == "answer"
    assert policy.DOMAIN_TO_ACTION["generator"] == "generate"
    assert policy.DOMAIN_TO_ACTION["simulation"] == "simulate"


def test_pipeline_order_is_actions_only():
    # S2 파이프라인 = generate→simulate (execute는 S5에서 추가). 도메인은 ACTION_TO_DOMAIN으로.
    assert policy.PIPELINE_ORDER == ("generate", "simulate")


def test_action_to_domain_is_inverse_of_domain_to_action():
    assert policy.ACTION_TO_DOMAIN == {
        "answer": "management",
        "generate": "generator",
        "simulate": "simulation",
    }
    for domain, action in policy.DOMAIN_TO_ACTION.items():
        assert policy.ACTION_TO_DOMAIN[action] == domain  # 역의 역은 자기 자신
