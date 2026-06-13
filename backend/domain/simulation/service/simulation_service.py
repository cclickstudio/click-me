# 시뮬레이션 오케스트레이션 서비스 — outer LangGraph 구동 + SSE 진행률
#
# _run 은 build_run_graph(P6) 컴파일본을 astream(updates)로 구동하며 노드별 진행률을 emit.
# 그래프 교체(mock ↔ 실 LLM)는 wiring.py 에서만. 결과 키는 분석팀 핸드오프 계약 유지.
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator

from domain.simulation.contracts.schemas import SimulationRunRequest

logger = logging.getLogger("clickme")


class SimulationService:
    """주입된 outer 그래프를 구동. 그래프 구성·어댑터는 wiring.py 가 결정·주입한다."""

    def __init__(self, *, graph, store) -> None:
        self._graph = graph
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

            state = {"request": request, "reactions": [], "personas": [], "rubric_scores": []}
            ad_dump: dict | None = None
            rubric_dump: list[dict] = []
            reactions: list[dict] = []
            aggregate_dump: dict | None = None
            total = request.sample_size
            done = 0

            async for update in self._graph.astream(state, stream_mode="updates"):
                for node, out in update.items():
                    if not out:
                        continue
                    if node == "interpret_ad":
                        ad_dump = out["ad"].model_dump()
                        store.emit(run_id, {"event": "progress", "stage": "panel", "pct": 15})
                    elif node == "load_panel":
                        total = len(out["personas"]) or total
                        store.emit(run_id, {"event": "progress", "stage": "reaction", "pct": 30})
                    elif node == "rubric_eval":
                        rubric_dump = [s.model_dump() for s in out["rubric_scores"]]
                    elif node == "react":
                        for r in out.get("reactions", []):
                            reactions.append(r.model_dump())  # §3.5 계약 (분석팀 입력)
                            done += 1
                            pct = 30 + int(done / total * 50) if total else 80
                            store.emit(
                                run_id,
                                {
                                    "event": "progress",
                                    "stage": "reaction",
                                    "pct": pct,
                                    "message": f"반응 {done}/{total}",
                                },
                            )
                    elif node == "aggregate":
                        store.emit(run_id, {"event": "milestone", "stage": "aggregate", "pct": 95})
                        aggregate_dump = out["aggregate"].model_dump()  # 집계 계약

            if not reactions:
                raise RuntimeError("모든 페르소나 반응 생성에 실패했습니다.")

            result = {
                "run_id": run_id,
                "ad_analysis": ad_dump,
                "reactions": reactions,
                "rubric_scores": rubric_dump,
                "aggregate": aggregate_dump,
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
