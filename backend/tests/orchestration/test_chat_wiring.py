# chat._resolve_domain — 라우터 판정이 도메인 문자열을 돌려준다(에이전트 빌드 없이 주입)
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router


def test_resolve_domain_uses_router(monkeypatch):
    import api.routers.chat as chat

    router = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    # monkeypatch로 주입 → 테스트 종료 시 자동 복원(전역 _orchestration 오염 방지)
    monkeypatch.setattr(chat, "_orchestration", (router, AgentRegistry()))

    assert chat._resolve_domain("이번 캠페인 예산?") == "management"
    assert chat._resolve_domain("안녕") == "clio"
