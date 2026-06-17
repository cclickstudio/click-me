# 반응 서브그래프 단위 테스트 — QA 재시도 루프 3분기(통과/재시도후통과/포기) 검증
from __future__ import annotations

from domain.simulation.contracts.schemas import AdInterpretation, Aisas, Persona, PersonaReaction
from domain.simulation.graph.reaction_graph import MAX_ATTEMPTS, build_reaction_graph, run_reaction


def _persona(pid: str = "P-1") -> Persona:
    return Persona(persona_id=pid, age=30, gender="F", region="서울", ocean={"openness": 0.5})


def _ad() -> AdInterpretation:
    return AdInterpretation(ad_id="AD-1")


class _StubReactor:
    """호출 횟수만 세고 고정 반응 반환(qa_passed는 게이트가 덮어씀)."""

    def __init__(self) -> None:
        self.calls = 0

    async def react(self, persona: Persona, ad: AdInterpretation) -> PersonaReaction:
        self.calls += 1
        return PersonaReaction(
            persona_id=persona.persona_id, aisas=Aisas(action=True), purchase_intent=3, trust=3
        )


class _Qa:
    """attempt >= pass_on 이면 통과. pass_on=None 이면 항상 탈락."""

    def __init__(self, pass_on: int | None) -> None:
        self.pass_on = pass_on

    async def check(
        self, reaction: PersonaReaction, attempt: int, *, persona=None, ad=None
    ) -> tuple[bool, str | None]:
        if self.pass_on is not None and attempt >= self.pass_on:
            return True, None
        return False, "stub_fail"


async def test_happy_path_passes_on_first_attempt() -> None:
    reactor = _StubReactor()
    graph = build_reaction_graph(reactor=reactor, qa=_Qa(pass_on=1))
    reaction = await run_reaction(graph, _persona(), _ad())

    assert reaction.qa_passed is True
    assert reaction.qa_fail_reason is None
    assert reactor.calls == 1


async def test_retry_then_pass() -> None:
    reactor = _StubReactor()
    graph = build_reaction_graph(reactor=reactor, qa=_Qa(pass_on=2))
    reaction = await run_reaction(graph, _persona(), _ad())

    assert reaction.qa_passed is True
    assert reactor.calls == 2  # 첫 시도 탈락 → 재생성 후 통과


async def test_give_up_after_max_attempts() -> None:
    reactor = _StubReactor()
    graph = build_reaction_graph(reactor=reactor, qa=_Qa(pass_on=None))
    reaction = await run_reaction(graph, _persona(), _ad())

    assert reaction.qa_passed is False  # 포기 → 집계에서 제외됨
    assert reaction.qa_fail_reason == "stub_fail"
    assert reactor.calls == MAX_ATTEMPTS
