# Planner — 단일/멀티스텝 build_plan(게이트 B), 도메인별 액션, fallback
from api.orchestration.planner import build_plan
from api.orchestration.routing import KeywordMatcher, Router


def test_single_step_management_uses_answer_action():
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("캠페인 예산")
    plan = build_plan(route, query="캠페인 예산")
    assert len(plan.steps) == 1
    assert plan.steps[0].domain == "management"
    assert plan.steps[0].action == "answer"
    assert plan.steps[0].inputs == {"query": "캠페인 예산"}


def test_single_step_generator_uses_generate_action():
    route = Router([KeywordMatcher("generator", frozenset({"시안"}))]).route("시안 만들어")
    plan = build_plan(route, query="시안 만들어")
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "generate"


def test_two_pipeline_domains_make_multistep_in_pipeline_order():
    router = Router(
        [
            KeywordMatcher("simulation", frozenset({"시뮬"})),  # 등록 순서를 일부러 뒤집어도
            KeywordMatcher("generator", frozenset({"시안"})),
        ]
    )
    route = router.route("시안 만들고 시뮬 돌려")
    plan = build_plan(route, query="시안 만들고 시뮬 돌려")
    # PIPELINE 순서(generate→simulate)로 정렬되어야 한다(라우터 점수/등록순 무관)
    assert [(s.domain, s.action) for s in plan.steps] == [
        ("generator", "generate"),
        ("simulation", "simulate"),
    ]


def test_sequential_marker_with_one_pipeline_domain_falls_back_to_single():
    # 순차마커 있어도 파이프라인 도메인이 1개면 단일 fallback(과생성·빈 Plan 방지)
    route = Router([KeywordMatcher("generator", frozenset({"시안"}))]).route("시안 그리고 뭐")
    plan = build_plan(route, query="시안 그리고 뭐")
    assert len(plan.steps) == 1
    assert plan.steps[0].domain == "generator"


def test_build_plan_rejects_unresolved_domain():
    import pytest

    # 미해석 라우트(score 0 → clio) 호출 시 명시적 ValueError(silent KeyError 대신).
    route = Router([KeywordMatcher("generator", frozenset({"시안"}))]).route("안녕")
    assert route.domain == "clio"  # 전제 — 키워드 미매칭
    with pytest.raises(ValueError):
        # "그리고" 순차마커 → 게이트 B 진입하지만 도메인 없음
        build_plan(route, query="그리고")
