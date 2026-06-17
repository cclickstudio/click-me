# 토론 파이프라인 오케스트레이션 — 결정론 조각(8·9·10-a·10-b)을 묶어 SSE로 단계별 진행 노출
#
# 7번(반응 출력) 산출물(reactions[] + ad_analysis)을 입력받아 8→9→10-a→10-b를 순차 실행하며
# store.emit 으로 단계 이벤트를 흘린다. 10-c(LLM 토론)·11(리포트)은 placeholder(다음 단계에서 구현).
# SSE/store 패턴은 simulation_service 와 동일(같은 InMemorySimulationStore 재사용 가능).
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable

from domain.simulation.contracts.debate_ports import DebaterPort, JudgePort
from domain.simulation.contracts.debate_schemas import DebateTopic
from domain.simulation.contracts.schemas import AdInterpretation, Persona, PersonaReaction
from domain.simulation.tools.debate.analyzer import analyze_reactions
from domain.simulation.tools.debate.assigner import assign_panel
from domain.simulation.tools.debate.kpi import (
    build_topic,
    build_topic_candidates,
    compute_kpi,
)
from domain.simulation.tools.debate.report import build_report
from domain.simulation.tools.debate.runner import run_debate
from domain.simulation.tools.debate.selector import RerankFn, select_panel

logger = logging.getLogger("clickme")


class DebateService:
    """토론 파이프라인 구동 — 결정론 조각 실행 + (엔진 주입 시) LLM 토론(10-c)을 라운드별 emit.

    debater_factory·judge가 주입되면 10-c 토론을 돌리고, 미주입이면 placeholder(골격)만 흘린다.
    엔진 교체(mock↔실 LLM)는 wiring에서만.
    """

    def __init__(
        self,
        *,
        store,
        debater_factory: Callable[[list[PersonaReaction]], DebaterPort] | None = None,
        judge: JudgePort | None = None,
        persistence=None,
        selector_rerank_fn: RerankFn | None = None,
    ) -> None:
        self._store = store
        self._debater_factory = debater_factory
        self._judge = judge
        self._persistence = persistence  # DebateRepository(주입 시 + simulation_id 있을 때 저장)
        # 일반인 선발(10-a) 동점 시 LLM 재랭킹(주입 시). None이면 결정론 선발(mock·무비용 경로).
        self._selector_rerank_fn = selector_rerank_fn

    def analyze(
        self,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
    ) -> dict:
        """조각 8·9만 — 반응 분석·KPI·토론 주제(결정론·LLM✗·동기). 토론 전 미리보기용.

        funnel·bottleneck·이탈/거부 분해·소비자 그룹(8) + 4대 KPI·토론 주제(9)를 즉시 반환.
        """
        analysis = analyze_reactions(reactions, ad_analysis)
        aggregate = compute_kpi(reactions)
        topic = build_topic(analysis, aggregate, ad_analysis)
        return {
            "analysis": analysis.model_dump(),
            "aggregate": aggregate.model_dump(),
            "topic": topic.model_dump(),
        }

    def build_candidates(
        self,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
    ) -> dict:
        """추가 토론용 논제 후보 5개(결정론·LLM✗). 사용자가 골라 start(topic=)로 전달.

        5가지 주신호를 진단형 대립 논제로 만들어 ranking·confidence 순으로 반환(변경2).
        """
        analysis = analyze_reactions(reactions, ad_analysis)
        aggregate = compute_kpi(reactions)
        topics = build_topic_candidates(analysis, aggregate, ad_analysis)
        return {"topics": [t.model_dump() for t in topics]}

    async def ask_question(
        self,
        run_id: str,
        question: str,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
    ) -> AsyncIterator[str]:
        """토론 종료 후 Q&A — 패널이 순차로 답변(SSE 스트림).

        run_id의 결과(패널 assigned·주제 topic)를 get_result로 복원하고, reactions로
        debater를 만들어 참가자별 answer_question을 순차 호출하며 qa_utterance를 yield.
        TODO(T2 Q&A): 본문 구현(현재는 계약 스텁).
        """
        if self._store.get_status(run_id) is None:
            yield 'data: {"event": "error", "message": "Run not found"}\n\n'
            return
        yield 'data: {"event": "error", "message": "Q&A 미구현(T2 트랙에서 구현 예정)"}\n\n'

    async def start(
        self,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
        *,
        simulation_id: str | None = None,
        lay_count: int = 3,
        personas: list[Persona] | None = None,
        topic: DebateTopic | None = None,
    ) -> str:
        """비동기 시작 — 백그라운드 실행 후 run_id 반환(진행률은 SSE, 결과는 get_result).

        lay_count: 일반인 수(2=피벗·비판자 / 3=+완주자 / 4=+완주자·미온). 패널 = 전문가4 + 일반인.
        personas: 인구통계(있으면 타깃 적합 선발 — 타깃 밖 후보 배제).
        topic: 추가 토론에서 사용자가 고른 논제(None이면 최초 토론 = 분석 headline 고정).
        """
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        asyncio.create_task(
            self._run(run_id, reactions, ad_analysis, simulation_id, lay_count, personas, topic)
        )
        return run_id

    async def run(
        self,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
        *,
        simulation_id: str | None = None,
        lay_count: int = 3,
        personas: list[Persona] | None = None,
    ) -> dict | None:
        """동기 실행 — 끝까지 돌린 뒤 결과(분석·KPI·주제·패널)를 반환."""
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        await self._run(run_id, reactions, ad_analysis, simulation_id, lay_count, personas)
        return self._store.get_result(run_id)

    async def _run(
        self,
        run_id: str,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None,
        simulation_id: str | None = None,
        lay_count: int = 3,
        personas: list[Persona] | None = None,
        selected_topic: DebateTopic | None = None,
    ) -> None:
        store = self._store
        try:
            store.set_status(run_id, "RUNNING")

            # ── 조각 8 반응 분석 ──
            analysis = analyze_reactions(reactions, ad_analysis)
            bn = analysis.bottleneck
            store.emit(
                run_id,
                {
                    "event": "progress",
                    "stage": "analysis",
                    "pct": 20,
                    "total_n": analysis.total_n,
                    "bottleneck": f"{bn.from_stage}->{bn.to_stage}" if bn else None,
                },
            )
            await asyncio.sleep(0)  # 협조적 양보(이벤트가 stream_events에 흘러가게)

            # ── 조각 9 KPI + 토론 주제 ──
            aggregate = compute_kpi(reactions)
            store.emit(
                run_id,
                {
                    "event": "progress",
                    "stage": "kpi",
                    "pct": 35,
                    "click_intent_rate": aggregate.click_intent_rate,
                    "trust_avg": aggregate.trust_avg,
                    "rejection_rate": aggregate.rejection_rate,
                },
            )
            # 추가 토론: 사용자가 고른 논제를 그대로 사용. 최초 토론: 분석 headline 고정(변경1).
            # build_topic이 만든 진단 기반 headline을 그대로 토론 주제로 쓴다(LLM refine 없음).
            if selected_topic is not None:
                topic = selected_topic
            else:
                topic = build_topic(analysis, aggregate, ad_analysis)
            store.emit(
                run_id,
                {
                    "event": "progress",
                    "stage": "topic",
                    "pct": 45,
                    "primary_signal": topic.primary_signal,
                    "headline": topic.headline,
                },
            )
            await asyncio.sleep(0)

            # ── 조각 10-a 구성(전문가 4 합성 + 일반인 lay_count 선발, personas 있으면 타깃 적합) ──
            # selector_rerank_fn 주입 시 동점 후보만 LLM 재랭킹(실 LLM 경로). mock은 None=결정론.
            panel = select_panel(
                reactions, ad_analysis, lay_count, personas, self._selector_rerank_fn
            )
            store.emit(
                run_id,
                {
                    "event": "progress",
                    "stage": "selection",
                    "pct": 60,
                    "count": len(panel.participants),
                    "pivot_id": panel.pivot_id,
                    "critic_secured": panel.critic_secured,
                },
            )

            # ── 조각 10-b 엔진·이름 배정 ──
            assigned = assign_panel(panel)
            store.emit(
                run_id,
                {
                    "event": "progress",
                    "stage": "assignment",
                    "pct": 75,
                    "judge_engine": assigned.judge_engine,
                    "roster": [
                        {"name": p.persona_name, "role": p.role, "engine": p.engine}
                        for p in assigned.participants
                    ],
                },
            )
            await asyncio.sleep(0)

            # ── 조각 10-c LLM 토론 (엔진 주입 시 실행, 아니면 placeholder) ──
            debate_dump: dict | None = None
            debate_obj = None
            if self._debater_factory is not None and self._judge is not None:
                debater = self._debater_factory(reactions)

                # 발언·라운드 정리를 실시간 emit(토론 과정 stream). store.emit은 스레드세이프.
                def _emit(ev: dict, _run_id: str = run_id) -> None:
                    self._store.emit(_run_id, ev)

                # LLM 엔진은 동기 블로킹 — 스레드로 분리해 이벤트 루프(다른 SSE 요청)를 막지 않는다.
                debate = await asyncio.to_thread(
                    run_debate, assigned, topic, debater, self._judge, _emit
                )
                debate_obj = debate
                store.emit(
                    run_id,
                    {
                        "event": "progress",
                        "stage": "judge_final",
                        "pct": 92,
                        "rounds_run": debate.rounds_run,
                        "stop_reason": debate.stop_reason,
                        "headline": debate.final.headline if debate.final else None,
                    },
                )
                debate_dump = debate.model_dump()
            else:
                store.emit(
                    run_id,
                    {
                        "event": "progress",
                        "stage": "debate",
                        "pct": 85,
                        "status": "pending",
                        "message": "LLM 토론(10-c) 엔진 미주입 — wiring에서 mock/실 엔진 주입 필요",
                    },
                )

            # ── 조각 11 리포트 (결정론 조립) ──
            report = build_report(analysis, aggregate, topic, debate_obj)
            store.emit(
                run_id,
                {
                    "event": "progress",
                    "stage": "report",
                    "pct": 98,
                    "headline": report.headline,
                    "debate_available": report.debate_available,
                    "actions": len(report.ranked_actions),
                },
            )

            # ── DB 영속화(주입 + simulation_id + 토론 있을 때만; FK상 실 simulations 행 필요) ──
            debate_id: str | None = None
            if self._persistence is not None and simulation_id and debate_obj is not None:
                try:
                    saved = await self._persistence.save(simulation_id, debate_obj)
                    debate_id = str(saved)
                    store.emit(
                        run_id,
                        {
                            "event": "progress",
                            "stage": "persisted",
                            "pct": 99,
                            "debate_id": debate_id,
                        },
                    )
                except Exception:
                    logger.exception("토론 영속화 실패(런은 유지) run_id=%s", run_id)

            result = {
                "run_id": run_id,
                "simulation_id": simulation_id,
                "debate_id": debate_id,
                "analysis": analysis.model_dump(),
                "aggregate": aggregate.model_dump(),
                "topic": topic.model_dump(),
                "panel": assigned.model_dump(),
                "debate": debate_dump,  # 조각 10-c 산출(엔진 주입 시)
                "report": report.model_dump(),  # 조각 11 산출
            }
            store.set_result(run_id, result)
            store.set_status(run_id, "COMPLETED")
            store.emit(run_id, {"event": "completed", "stage": "completed", "pct": 100})
        except Exception as exc:
            store.set_status(run_id, "FAILED")
            store.emit(run_id, {"event": "error", "message": str(exc)})
            logger.exception("토론 파이프라인 실패 run_id=%s", run_id)

    async def stream_events(self, run_id: str) -> AsyncIterator[str]:
        """SSE — store에 쌓인 이벤트를 폴링하며 흘린다(simulation_service와 동일 패턴)."""
        if self._store.get_status(run_id) is None:
            yield 'data: {"event": "error", "message": "Run not found"}\n\n'
            return
        sent = 0
        while True:
            events = self._store.get_events(run_id)
            while sent < len(events):
                yield f"data: {json.dumps(events[sent], ensure_ascii=False)}\n\n"
                sent += 1
            if self._store.get_status(run_id) in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.5)

    def get_result(self, run_id: str) -> dict | None:
        return self._store.get_result(run_id)
