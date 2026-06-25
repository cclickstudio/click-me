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
from datetime import UTC, datetime

from langsmith import traceable

from domain.simulation.contracts.debate_ports import DebaterPort, JudgePort
from domain.simulation.contracts.debate_schemas import (
    DebateDigest,
    DebateResult,
    DebateTopic,
    JudgeFinal,
    ParticipantDebate,
    SelectedPanel,
    Utterance,
)
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    ObjectiveFit,
    Persona,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
)
from domain.simulation.tools.debate.analyzer import analyze_reactions
from domain.simulation.tools.debate.assigner import assign_panel
from domain.simulation.tools.debate.kpi import (
    build_topic,
    build_topic_candidates,
    compute_kpi,
)
from domain.simulation.tools.debate.qa import stream_qa
from domain.simulation.tools.debate.report import (
    build_debate_digest,
    build_report,
    build_report_view,
)
from domain.simulation.tools.debate.runner import run_debate
from domain.simulation.tools.debate.selector import RerankFn, select_panel

logger = logging.getLogger("clickme")


def _usage_delta(
    before: dict[str, dict[str, int]], after: dict[str, dict[str, int]]
) -> dict[str, dict[str, int]]:
    """토론 전후 누적 토큰 스냅샷 차이 → 엔진별 1회 사용량 + total. 호출 없던 엔진은 생략."""
    by_engine: dict[str, dict[str, int]] = {}
    total = {"input": 0, "output": 0, "calls": 0}
    for engine, a in after.items():
        b = before.get(engine, {})
        d = {k: a.get(k, 0) - b.get(k, 0) for k in ("input", "output", "calls")}
        if any(d.values()):
            by_engine[engine] = d
            for k in total:
                total[k] += d[k]
    by_engine["total"] = total
    return by_engine


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
        sim_session_factory=None,
        selector_rerank_fn: RerankFn | None = None,
        usage_clients=None,
    ) -> None:
        self._store = store
        self._debater_factory = debater_factory
        self._judge = judge
        self._persistence = persistence  # DebateRepository(주입 시 + simulation_id 있을 때 저장)
        # 시뮬 결과 재조회용 세션 팩토리(get_saved_report 재조립). 미주입이면 복원 불가(None).
        self._sim_session_factory = sim_session_factory
        # 일반인 선발(10-a) 동점 시 LLM 재랭킹(주입 시). None이면 결정론 선발(mock·무비용 경로).
        self._selector_rerank_fn = selector_rerank_fn
        # 토론자·Judge가 공유하는 _Clients(실 LLM 경로만). 토론 전후 스냅샷 차이로 1회 토큰 집계.
        self._usage_clients = usage_clients

    def analyze(
        self,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
        ad_title: str | None = None,
        ad_description: str | None = None,
    ) -> dict:
        """조각 8·9만 — 반응 분석·KPI·토론 주제(결정론·LLM✗·동기). 토론 전 미리보기용.

        funnel·bottleneck·이탈/거부 분해·소비자 그룹(8) + 4대 KPI·토론 주제(9)를 즉시 반환.
        topic에 광고 제목·설명·해석이 동봉돼 토론자 grounding과 동일 맥락을 미리보기로 노출.
        """
        analysis = analyze_reactions(reactions, ad_analysis)
        aggregate = compute_kpi(reactions)
        topic = build_topic(analysis, aggregate, ad_analysis, ad_title, ad_description)
        return {
            "analysis": analysis.model_dump(),
            "aggregate": aggregate.model_dump(),
            "topic": topic.model_dump(),
        }

    def build_candidates(
        self,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
        ad_title: str | None = None,
        ad_description: str | None = None,
    ) -> dict:
        """추가 토론용 논제 후보 5개(결정론·LLM✗). 사용자가 골라 start(topic=)로 전달.

        5가지 주신호를 진단형 대립 논제로 만들어 ranking·confidence 순으로 반환(변경2).
        각 후보에 광고 제목·설명·해석을 동봉 — 사용자가 고른 논제가 그대로 토론자 grounding이 된다.
        """
        analysis = analyze_reactions(reactions, ad_analysis)
        aggregate = compute_kpi(reactions)
        topics = build_topic_candidates(analysis, aggregate, ad_analysis, ad_title, ad_description)
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
        """
        result = self.get_result(run_id)
        if result is None:
            yield 'data: {"event": "error", "message": "결과 없음 또는 토론 미완료"}\n\n'
            return
        if self._debater_factory is None:
            yield 'data: {"event": "error", "message": "토론 엔진 미주입 — Q&A 불가"}\n\n'
            return
        debater = self._debater_factory(reactions)

        # Q&A 1회(참가자 순차 답변)를 LangSmith 단일 트레이스로 묶는다 — 내부 answer_question
        # LLM 호출(wrap된 클라이언트)이 이 부모 run의 자식으로 중첩된다(토론 묶기와 동일 패턴).
        @traceable(run_type="chain", name="Q&A", metadata={"question": question[:100]})
        async def _qa_traced() -> AsyncIterator[str]:
            async for chunk in stream_qa(result, question, debater):
                yield chunk

        async for chunk in _qa_traced():
            yield chunk

    async def start(
        self,
        reactions: list[PersonaReaction],
        ad_analysis: AdInterpretation | None = None,
        *,
        simulation_id: str | None = None,
        lay_count: int = 3,
        personas: list[Persona] | None = None,
        topic: DebateTopic | None = None,
        rubric: list[RubricScore] | None = None,
        objective_fit: ObjectiveFit | None = None,
        ad_title: str | None = None,
        ad_description: str | None = None,
    ) -> str:
        """비동기 시작 — 백그라운드 실행 후 run_id 반환(진행률은 SSE, 결과는 get_result).

        lay_count: 일반인 수(2=피벗·비판자 / 3=+완주자 / 4=+완주자·미온). 패널 = 전문가4 + 일반인.
        personas: 인구통계(있으면 타깃 적합 선발 — 타깃 밖 후보 배제).
        topic: 추가 토론에서 사용자가 고른 논제(None이면 최초 토론 = 분석 headline 고정).
        rubric: §4 루브릭 점수(있으면 리포트 크리에이티브 진단에 그대로 실음).
        objective_fit: 캠페인 목표 적합도(ReportView 메인 판정 — DB 영속 없어 직접 전달).
        """
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        asyncio.create_task(
            self._run(
                run_id,
                reactions,
                ad_analysis,
                simulation_id,
                lay_count,
                personas,
                topic,
                rubric,
                objective_fit,
                ad_title,
                ad_description,
            )
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
        rubric: list[RubricScore] | None = None,
        objective_fit: ObjectiveFit | None = None,
        ad_title: str | None = None,
        ad_description: str | None = None,
    ) -> dict | None:
        """동기 실행 — 끝까지 돌린 뒤 결과(분석·KPI·주제·패널·리포트뷰)를 반환."""
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        await self._run(
            run_id,
            reactions,
            ad_analysis,
            simulation_id,
            lay_count,
            personas,
            rubric=rubric,
            objective_fit=objective_fit,
            ad_title=ad_title,
            ad_description=ad_description,
        )
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
        rubric: list[RubricScore] | None = None,
        objective_fit: ObjectiveFit | None = None,
        ad_title: str | None = None,
        ad_description: str | None = None,
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
                topic = build_topic(analysis, aggregate, ad_analysis, ad_title, ad_description)
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
            @traceable(
                run_type="chain",
                name="토론 대표 선발",
                metadata={
                    "domain": "simulation",
                    "feature": "debate",
                    "stage": "selection",
                    "run_id": run_id,
                    "lay_count": lay_count,
                    "reaction_count": len(reactions),
                    "has_personas": bool(personas),
                },
            )
            def _select_panel_traced() -> SelectedPanel:
                return select_panel(
                    reactions, ad_analysis, lay_count, personas, self._selector_rerank_fn
                )

            panel = _select_panel_traced()
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
            # seed=run_id로 토론마다 참가자 이름을 다양화(같은 run_id 안에서는 일관·재현).
            assigned = assign_panel(panel, seed=run_id)
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

                # 토론 토큰 = (토론 후 - 토론 전) 누적 스냅샷 차이. 동시 토론 시 합산될 수 있음.
                usage_before = self._usage_clients.usage_snapshot() if self._usage_clients else None

                # 토론 1회를 LangSmith 단일 트레이스로 묶는다 — 내부 LLM 호출(wrap된 클라이언트)이
                # 이 부모 run의 자식으로 중첩된다(개별 호출이 따로따로 올라가던 것 → 토론 1트리).
                @traceable(
                    run_type="chain",
                    name="토론",
                    metadata={"topic": topic.headline, "lay_count": lay_count},
                )
                def _run_debate_traced() -> DebateResult:
                    return run_debate(assigned, topic, debater, self._judge, _emit)

                # LLM 엔진은 동기 블로킹 — 스레드로 분리해 이벤트 루프(다른 SSE 요청)를 막지 않는다.
                # to_thread가 현재 컨텍스트를 스레드로 복사하므로 trace 중첩이 유지된다.
                debate = await asyncio.to_thread(_run_debate_traced)
                debate_obj = debate
                usage = None
                if usage_before is not None:
                    usage = _usage_delta(usage_before, self._usage_clients.usage_snapshot())
                    logger.info("토론 토큰 사용량 run_id=%s usage=%s", run_id, usage)
                store.emit(
                    run_id,
                    {
                        "event": "progress",
                        "stage": "judge_final",
                        "pct": 92,
                        "rounds_run": debate.rounds_run,
                        "stop_reason": debate.stop_reason,
                        "headline": debate.final.headline if debate.final else None,
                        "usage": usage,  # 엔진별 input/output/calls + total(실 LLM 경로만)
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
            report = build_report(analysis, aggregate, topic, debate_obj, rubric)
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

            # ── 추가 토론 합산: 이 시뮬의 모든 토론(기존+현재) 요약을 누적 ──
            # 같은 simulation_id로 토론을 거듭하면 digest가 쌓여 리포트 내용이 늘어난다(DB 무관).
            debates_digests: list[DebateDigest] = []
            if debate_obj is not None:
                current_digest = build_debate_digest(topic, debate_obj, debate_id)
                if simulation_id:
                    prior = [DebateDigest(**d) for d in store.get_debate_digests(simulation_id)]
                    debates_digests = [*prior, current_digest]
                    store.add_debate_digest(simulation_id, current_digest.model_dump())
                else:
                    debates_digests = [current_digest]

            # ── 통합 ReportView 조립(화면·PDF 공용 단일 소스) — 시뮬+토론 종합 ──
            report_view = build_report_view(
                run_id=run_id,
                simulation_id=simulation_id,
                debate_id=debate_id,
                report=report,
                objective_fit=objective_fit,
                ad_analysis=ad_analysis,
                ad=None,  # 광고 선언 입력은 시뮬 result['ad']에만(추후 DebateRequest로 전달)
                topic=topic,
                debate=debate_obj,
                aggregate=aggregate,
                analysis=analysis,
                personas=personas or [],
                reactions=reactions,
                generated_at=datetime.now(UTC).isoformat(),
                debates=debates_digests,
            )

            # report_view는 결정론 파생물(LLM✗) — 별도 영속화하지 않는다(중복·stale 방지).
            # 조회 시 get_saved_report가 시뮬 결과 + 저장 토론으로 재조립한다.

            result = {
                "run_id": run_id,
                "simulation_id": simulation_id,
                "debate_id": debate_id,
                "ad_analysis": ad_analysis.model_dump() if ad_analysis else None,  # §0 헤더(PDF)용
                "analysis": analysis.model_dump(),
                "aggregate": aggregate.model_dump(),
                "topic": topic.model_dump(),
                "panel": assigned.model_dump(),
                "debate": debate_dump,  # 조각 10-c 산출(엔진 주입 시)
                "report": report.model_dump(),  # 조각 11 산출
                "report_view": report_view.model_dump(),  # 통합 리포트(화면·PDF 단일 소스)
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

    async def list_saved(self, simulation_id: str) -> list[dict]:
        """simulation_id로 저장된 토론 목록(메타). 영속화 미주입(DB 없음)이면 빈 목록."""
        if self._persistence is None:
            return []
        return await self._persistence.list_by_simulation(simulation_id)

    async def get_saved(self, debate_id: str) -> dict | None:
        """debate_id로 저장된 토론 상세(복원·표시용). 영속화 미주입이면 None."""
        if self._persistence is None:
            return None
        return await self._persistence.get_detail(debate_id)

    async def get_saved_report(self, simulation_id: str) -> dict | None:
        """simulation_id로 통합 리포트(report_view)를 재조립해 반환. report_view는 결정론
        파생물(LLM✗)이라 저장 결과 + 저장 토론만 있으면 언제든 재조립된다(별도 영속화 없음).

        시뮬 결과 없음 / 토론 0개(최종 리포트는 토론 후 산출) / 예외 → None(로깅).
        """
        if self._sim_session_factory is None or self._persistence is None:
            return None
        try:
            return await self._rebuild_report(simulation_id)
        except Exception:
            logger.exception("통합 리포트 재조립 실패 simulation_id=%s", simulation_id)
            return None

    async def _rebuild_report(self, simulation_id: str) -> dict | None:
        """시뮬 결과(DB) + 저장 토론(DB)을 contracts 객체로 복원해 ReportView를 재조립."""
        import uuid as _uuid

        from domain.simulation.repositories.simulation_repository import SimulationRepository

        # ── 시뮬 결과 복원 ──
        async with self._sim_session_factory() as session:
            full = await SimulationRepository(session).get_full_result(
                _uuid.UUID(str(simulation_id))
            )
        if full is None:
            return None

        ad_analysis = (
            AdInterpretation.model_validate(full["ad_analysis"])
            if full.get("ad_analysis")
            else None
        )
        personas = [Persona.model_validate(p) for p in full.get("personas", [])]
        reactions = [PersonaReaction.model_validate(r) for r in full.get("reactions", [])]
        rubric = [RubricScore.model_validate(s) for s in full.get("rubric_scores", [])]
        aggregate = (
            SimulationAggregate.model_validate(full["aggregate"]) if full.get("aggregate") else None
        )
        objective_fit = (
            ObjectiveFit.model_validate(full["objective_fit"])
            if full.get("objective_fit")
            else None
        )
        if aggregate is None or not reactions:
            return None

        analysis = analyze_reactions(reactions, ad_analysis)

        # ── 저장 토론 복원(0개면 None — 최종 리포트는 토론 후 산출) ──
        metas = await self._persistence.list_by_simulation(simulation_id)
        if not metas:
            return None

        digests: list[DebateDigest] = []
        main_debate: DebateResult | None = None
        main_topic: DebateTopic | None = None
        main_debate_id: str | None = None
        # list_by_simulation은 최신순 — 정렬 누적은 오래된→최신, 메인은 최신(첫 항목).
        for idx, meta in enumerate(metas):
            debate_id = meta.get("debate_id")
            detail = await self._persistence.get_detail(debate_id)
            if detail is None:
                continue
            debate_obj = self._detail_to_debate_result(detail)
            topic = build_topic(analysis, aggregate, ad_analysis)
            # 저장된 headline로 메인 topic의 표시 문구를 맞춘다(diagnosis 등 진단은 재생성값 유지).
            if detail.get("topic"):
                topic = topic.model_copy(update={"headline": detail["topic"]})
            digests.append(build_debate_digest(topic, debate_obj, debate_id))
            if idx == 0:  # 최신 토론을 메인으로
                main_debate = debate_obj
                main_topic = topic
                main_debate_id = debate_id
        if main_debate is None:
            return None
        digests.reverse()  # 오래된→최신 누적 순서로

        report = build_report(analysis, aggregate, main_topic, main_debate, rubric)
        report_view = build_report_view(
            run_id=str(simulation_id),
            simulation_id=str(simulation_id),
            debate_id=main_debate_id,
            report=report,
            objective_fit=objective_fit,
            ad_analysis=ad_analysis,
            ad=None,
            topic=main_topic,
            debate=main_debate,
            aggregate=aggregate,
            analysis=analysis,
            personas=personas,
            reactions=reactions,
            generated_at=datetime.now(UTC).isoformat(),
            debates=digests,
        )
        return report_view.model_dump(mode="json")

    @staticmethod
    def _detail_to_debate_result(detail: dict) -> DebateResult:
        """get_detail(dict) → DebateResult 복원. participants는 발언을 라운드순으로 다시 묶는다."""
        # 발언(평면 리스트)을 persona_id로 그룹핑.
        utt_by_pid: dict[str, list[Utterance]] = {}
        for u in detail.get("utterances", []):
            pid = u.get("persona_id")
            if pid is None:
                continue
            utt_by_pid.setdefault(pid, []).append(
                Utterance(
                    round=u["round"],
                    phase=u["phase"],
                    stance=u["stance"],
                    text=u["text"],
                    reason=u.get("reason", ""),
                    lever=u.get("lever", ""),
                )
            )
        participants = [
            ParticipantDebate(
                persona_id=p["persona_id"],
                persona_name=p["persona_name"],
                persona_profile=p.get("persona_profile", ""),
                role=p["role"],
                engine=p["engine"],
                utterances=utt_by_pid.get(p["persona_id"], []),
            )
            for p in detail.get("participants", [])
        ]
        final_d = detail.get("final")
        final = JudgeFinal.model_validate(final_d) if final_d else None
        # round_summaries 키는 JSON 직렬화로 str일 수 있음 → int로 환원(스키마는 dict[int, str]).
        rs_raw = detail.get("round_summaries") or {}
        round_summaries = {int(k): v for k, v in rs_raw.items()}
        return DebateResult(
            topic=detail.get("topic") or "",
            rounds_run=detail.get("rounds_run") or 0,
            stop_reason=detail.get("stop_reason") or "",
            models=detail.get("models") or {},
            participants=participants,
            round_summaries=round_summaries,
            final=final,
        )
