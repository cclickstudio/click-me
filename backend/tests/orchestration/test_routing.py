# Router 점수 라우팅 — 매칭·tie·ambiguous·default·candidates 검증
from api.orchestration.routing import Candidate, KeywordMatcher, Router


def _router_two():
    # 동점 검증용: 같은 키워드를 가진 두 도메인(등록 순서 zzz 먼저)
    return Router(
        [KeywordMatcher("zzz", frozenset({"x"})), KeywordMatcher("aaa", frozenset({"x"}))]
    )


def test_keyword_hit_routes_to_domain():
    r = Router([KeywordMatcher("management", frozenset({"캠페인", "예산"}))])
    d = r.route("이번 캠페인 예산 어때")
    assert d.domain == "management"
    assert d.score > 0.0


def test_no_hit_falls_back_to_default():
    r = Router([KeywordMatcher("management", frozenset({"캠페인"}))], default="clio")
    d = r.route("안녕하세요")
    assert d.domain == "clio"
    assert d.score == 0.0
    assert d.ambiguous is False


def test_tie_breaker_is_registration_order_not_domain_name():
    # 두 도메인 점수 동일 → 알파벳('aaa')이 아니라 등록 순서('zzz')가 이긴다
    d = _router_two().route("x")
    assert d.domain == "zzz"


def test_ambiguous_true_only_when_real_competitor():
    # 박빙 경쟁(점수 동일) → ambiguous True
    d = _router_two().route("x")
    assert d.ambiguous is True


def test_single_low_score_is_not_ambiguous():
    # 단독 저점수 후보는 ambiguous 아님(runner=0)
    r = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    d = r.route("캠페인")
    assert d.ambiguous is False


def test_candidates_preserved_in_decision():
    d = _router_two().route("x")
    assert d.candidates == tuple(sorted(d.candidates, key=lambda c: c.score, reverse=True))
    assert {c.domain for c in d.candidates} == {"zzz", "aaa"}
    assert all(isinstance(c, Candidate) for c in d.candidates)


def test_router_ambiguity_margin_comes_from_policy(monkeypatch):
    # 마진을 policy에서 읽는지 — 큰 값으로 패치하면 평소 비애매 케이스가 애매가 된다.
    from api.orchestration import policy

    monkeypatch.setattr(policy, "ROUTER_AMBIGUITY_MARGIN", 0.9)
    r = Router(
        [KeywordMatcher("a", frozenset({"x", "y", "z"})), KeywordMatcher("b", frozenset({"x"}))]
    )
    d = r.route("x y z")  # a=3hit→1.0, b=1hit→0.333, 차=0.667 < 0.9 → ambiguous
    assert d.ambiguous is True
