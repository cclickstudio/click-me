# 반응 유닛 — 페르소나 1명 반응 생성 + QA 게이트(재시도 루프) LangGraph 서브그래프
#
# 토폴로지: gen_reaction → qa_gate →(retry) gen_reaction /(done) END
# 통과 또는 최대 시도 도달 시 종료. 포기 시 qa_passed=False로 반환 → 집계가 자동 제외.
# reactor·qa 는 덕타이핑 주입(Protocol 포트 없음). 실 LLM/QA 어댑터는 wiring.py에서 교체.
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from domain.simulation.contracts.schemas import AdInterpretation, Persona, PersonaReaction

MAX_ATTEMPTS = 2


class ReactionState(TypedDict):
    """서브그래프 상태 — 페르소나 1명 단위."""

    persona: Persona
    ad: AdInterpretation
    attempts: int
    reaction: PersonaReaction | None


def build_reaction_graph(*, reactor, qa):
    """반응+QA 재시도 서브그래프를 컴파일한다.

    기대 어댑터(덕타이핑):
      async reactor.react(persona, ad) -> PersonaReaction
      async qa.check(reaction, attempt, *, persona, ad) -> (passed, reason)
    """

    async def gen_reaction(state: ReactionState) -> dict:
        reaction = await reactor.react(state["persona"], state["ad"])
        return {"reaction": reaction, "attempts": state["attempts"] + 1}

    async def qa_gate(state: ReactionState) -> dict:
        # persona·ad 도 전달 — LLM QA(광고무관·설정모순) 판정용(규칙 QA는 무시). check 비동기.
        passed, reason = await qa.check(
            state["reaction"], state["attempts"], persona=state["persona"], ad=state["ad"]
        )
        updated = state["reaction"].model_copy(
            update={"qa_passed": passed, "qa_fail_reason": reason}
        )
        return {"reaction": updated}

    def route(state: ReactionState) -> str:
        reaction = state["reaction"]
        if reaction.qa_passed:
            return "done"
        if state["attempts"] >= MAX_ATTEMPTS:
            return "done"  # 포기 — qa_passed=False 유지, 집계에서 제외
        return "retry"

    graph = StateGraph(ReactionState)
    graph.add_node("gen_reaction", gen_reaction)
    graph.add_node("qa_gate", qa_gate)
    graph.add_edge(START, "gen_reaction")
    graph.add_edge("gen_reaction", "qa_gate")
    graph.add_conditional_edges("qa_gate", route, {"retry": "gen_reaction", "done": END})
    return graph.compile()


async def run_reaction(graph, persona: Persona, ad: AdInterpretation) -> PersonaReaction:
    """서브그래프 1회 실행 → 최종 PersonaReaction 반환."""
    final = await graph.ainvoke({"persona": persona, "ad": ad, "attempts": 0, "reaction": None})
    return final["reaction"]
