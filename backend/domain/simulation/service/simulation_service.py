# 시뮬레이션 오케스트레이션 서비스 — 어댑터 주입(DI), 파이프라인 실행 + SSE 진행률
#
# 파이프라인: 광고해석 → 패널/페르소나 → 반응(동시) → 루브릭 → 집계 → [분석팀 핸드오프]
# 어댑터 교체(mock ↔ 실 LLM)는 wiring.py의 use_mock 분기로만. (Protocol 포트 없이 덕타이핑)
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator

from domain.simulation.contracts.schemas import PanelSpec, SimulationRunRequest

logger = logging.getLogger("clickme")

_CONCURRENCY = 5


class SimulationService:
    """주입된 어댑터로 파이프라인을 실행. 구체 어댑터는 wiring.py가 결정·주입한다.

    기대 어댑터(덕타이핑):
      interpreter.interpret(request) -> AdInterpretation
      panel.get_or_build(spec)       -> (panel_version, [Persona])
      reactor.react(persona, ad)     -> PersonaReaction
      rubric.evaluate(ad)            -> [RubricScore]
      aggregator.aggregate([reaction]) -> SimulationAggregate
      store: 실행 상태·이벤트·결과 보관
    """

    def __init__(self, *, interpreter, panel, reactor, rubric, aggregator, store) -> None:
        self._interpreter = interpreter
        self._panel = panel
        self._reactor = reactor
        self._rubric = rubric
        self._aggregator = aggregator
        self._store = store

    async def start(self, request: SimulationRunRequest) -> str:
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        asyncio.create_task(self._run(run_id, request))
        return run_id

    async def _run(self, run_id: str, request: SimulationRunRequest) -> None:
        store = self._store
        try:
            store.set_status(run_id, "RUNNING")
            store.emit(run_id, {"event": "progress", "stage": "ad_analysis", "pct": 5})
            ad = await self._interpreter.interpret(request)

            store.emit(run_id, {"event": "progress", "stage": "panel", "pct": 15})
            spec = PanelSpec(size=request.sample_size, target_filter=request.target_filter)
            _panel_version, personas = await self._panel.get_or_build(spec)

            total = len(personas)
            store.emit(run_id, {"event": "progress", "stage": "reaction", "pct": 30})
            sem = asyncio.Semaphore(_CONCURRENCY)
            done = 0

            async def react(persona) -> object | None:
                nonlocal done
                async with sem:
                    try:
                        result = await self._reactor.react(persona, ad)
                    except Exception as exc:  # 한 명 실패는 건너뜀 (전체 진행 유지)
                        logger.warning("페르소나 %s 반응 실패: %s", persona.persona_id, exc)
                        return None
                    done += 1
                    pct = 30 + int(done / total * 50)
                    store.emit(
                        run_id,
                        {
                            "event": "progress",
                            "stage": "reaction",
                            "pct": pct,
                            "message": f"반응 {done}/{total}",
                        },
                    )
                    return result

            raw = await asyncio.gather(*[react(p) for p in personas])
            reactions = [r for r in raw if r is not None]
            if not reactions:
                raise RuntimeError("모든 페르소나 반응 생성에 실패했습니다.")

            store.emit(run_id, {"event": "progress", "stage": "rubric", "pct": 85})
            rubric_scores = await self._rubric.evaluate(ad)

            store.emit(run_id, {"event": "milestone", "stage": "aggregate", "pct": 95})
            aggregate = self._aggregator.aggregate(reactions)

            result = {
                "run_id": run_id,
                "ad_analysis": ad.model_dump(),
                "reactions": [r.model_dump() for r in reactions],  # §3.5 계약 (분석팀 입력)
                "rubric_scores": [s.model_dump() for s in rubric_scores],
                "aggregate": aggregate.model_dump(),  # 집계 계약 (분석팀·리포트 입력)
            }
            store.set_result(run_id, result)
            store.set_status(run_id, "COMPLETED")
            store.emit(
                run_id, {"event": "completed", "result_url": f"/api/simulate/{run_id}/result"}
            )
        except Exception as exc:
            store.set_status(run_id, "FAILED")
            store.emit(run_id, {"event": "error", "message": str(exc)})
            logger.exception("시뮬레이션 실패 run_id=%s", run_id)

    async def stream_events(self, run_id: str) -> AsyncIterator[str]:
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
