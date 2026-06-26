# chat._should_plan — 라우터 판정 + 등록 여부로 Plan 경로 진입을 결정(에이전트 빌드 없이 주입)
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router


class _FakeAgent:
    domain = "management"

    async def ask(self, req):
        return req


def test_should_plan_true_for_registered_resolved_domain(monkeypatch):
    import api.routers.chat as chat

    router = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    registry = AgentRegistry()
    registry.register(_FakeAgent())
    monkeypatch.setattr(chat, "_orchestration", (router, registry))

    route = router.route("이번 캠페인 예산?")
    assert chat._should_plan(route, registry) is True


def test_should_plan_false_for_default_clio(monkeypatch):
    import api.routers.chat as chat

    router = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    registry = AgentRegistry()
    registry.register(_FakeAgent())
    monkeypatch.setattr(chat, "_orchestration", (router, registry))

    route = router.route("안녕")  # score 0 → clio
    assert chat._should_plan(route, registry) is False


def test_should_plan_false_when_domain_unregistered(monkeypatch):
    import api.routers.chat as chat

    router = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    empty = AgentRegistry()  # management 미등록
    monkeypatch.setattr(chat, "_orchestration", (router, empty))

    route = router.route("이번 캠페인 예산?")
    assert chat._should_plan(route, empty) is False
