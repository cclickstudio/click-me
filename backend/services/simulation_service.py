from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

logger = logging.getLogger("clickme")

from core.schemas import SimulationRequest, Persona
from tools.simulation.ssr_scorer import SSRScorer
from tools.ad_analysis.vision import run_ad_understanding
from tools.persona.factory import run_persona_factory
from tools.simulation.exposure import run_exposure
from tools.simulation.deliberation import run_deliberation

_tasks: dict[str, dict] = {}


async def start_simulation(request: SimulationRequest, ssr_scorer: SSRScorer) -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "pending", "result": None, "events": []}
    asyncio.create_task(_run_pipeline(task_id, request, ssr_scorer))
    return task_id


async def _run_pipeline(task_id: str, request: SimulationRequest, ssr_scorer: SSRScorer) -> None:
    store = _tasks[task_id]

    def emit(event: dict) -> None:
        store["events"].append(event)

    try:
        store["status"] = "running"
        emit({"event": "progress", "stage": "ad_analysis", "pct": 5, "message": "광고 분석 중..."})

        ad_analysis = await run_ad_understanding(
            ad_id=request.simulation_id,
            ad_type="image",
            ad_content=str(request.ad_analysis),
        )
        emit({"event": "progress", "stage": "persona_factory", "pct": 15, "message": "페르소나 생성 중..."})

        personas = await run_persona_factory(
            simulation_id=request.simulation_id,
            count=request.persona_set.get("size", 20),
            ad_analysis=ad_analysis.model_dump(),
        )
        emit({"event": "progress", "stage": "exposure", "pct": 30, "message": f"반응 시뮬레이션 중 (0/{len(personas)})"})

        ssr_results: list[dict] = []
        sem = asyncio.Semaphore(5)

        async def process_persona(idx: int, persona: Persona) -> dict | None:
            async with sem:
                try:
                    exposure = await run_exposure(persona, ad_analysis.model_dump())

                    pct = 30 + int((idx + 1) / len(personas) * 30)
                    emit({"event": "progress", "stage": "exposure", "pct": pct, "message": f"반응 시뮬레이션 중 ({idx+1}/{len(personas)})"})

                    deliberation = await run_deliberation(persona, exposure, ad_analysis.model_dump())

                    text = SSRScorer.build_input_text(exposure, deliberation)
                    signals = await ssr_scorer.score(text)
                    return {
                        "persona_id": persona.persona_id,
                        "signals": {dim: d.model_dump() for dim, d in signals.items()},
                        "free_text": (
                            f"{exposure.get('gut_reaction', '')} "
                            f"{deliberation.get('final_attitude', '')}"
                        ),
                        "confidence": float(1.0 - signals["click_intent"].std / 0.5),
                    }
                except Exception as exc:
                    logger.warning("페르소나 %s 처리 실패 (건너뜀): %s", persona.persona_id, exc)
                    return None

        raw_results = await asyncio.gather(*[process_persona(i, p) for i, p in enumerate(personas)])
        ssr_results = [r for r in raw_results if r is not None]

        if not ssr_results:
            raise RuntimeError("모든 페르소나 처리에 실패했습니다. API 키 또는 네트워크를 확인하세요.")

        emit({"event": "milestone", "message": "집계 완료", "pct": 90})

        n = len(ssr_results)

        def avg_probs(dim: str) -> list[float]:
            all_p = [s["signals"][dim]["raw_probs"] for s in ssr_results if dim in s["signals"]]
            if not all_p:
                return [0.2] * 5
            return [sum(p[i] for p in all_p) / n for i in range(len(all_p[0]))]

        def avg_mean(dim: str) -> float:
            vals = [s["signals"][dim]["mean"] for s in ssr_results if dim in s["signals"]]
            return sum(vals) / len(vals) if vals else 0.0

        purchase_dist = avg_probs("conversion_intent")
        att = avg_mean("attention")
        comp = avg_mean("comprehension")
        clk = avg_mean("click_intent")
        conv = avg_mean("conversion_intent")

        result = {
            "simulation_id": request.simulation_id,
            "task_id": task_id,
            "status": "completed",
            "p0": {
                "persona_reactions": [
                    {
                        "persona_id": r["persona_id"],
                        "free_text_reaction": r.get("free_text", ""),
                        "purchase_intent_distribution": r["signals"].get("conversion_intent", {}).get("raw_probs", [0.2] * 5),
                    }
                    for r in ssr_results
                ],
                "aggregate_purchase_intent": purchase_dist,
                "kobaco_comparable": True,
            },
            "p1": {
                "signal_distributions": {
                    dim: {
                        "mean": avg_mean(dim), "std": 0.1,
                        "p10": max(0.0, avg_mean(dim) - 0.2),
                        "p90": min(1.0, avg_mean(dim) + 0.2),
                        "raw_probs": avg_probs(dim),
                    }
                    for dim in ["attention", "sentiment", "click_intent", "comprehension", "recall"]
                },
                "kpi": {"ctr": round(clk, 3), "cvr": round(conv, 3), "net_sentiment": round(avg_mean("sentiment"), 3)},
                "funnel": {"attention": round(att, 3), "comprehension": round(comp, 3), "click": round(clk, 3), "conversion": round(conv, 3)},
                "langsmith_trace_url": None,
                "note": "P1 신호는 탐색적(exploratory). 인간 ground truth 없음.",
            },
        }

        store["result"] = result
        store["status"] = "completed"
        emit({"event": "completed", "result_url": f"/api/simulate/{task_id}/result"})

    except Exception as exc:
        store["status"] = "failed"
        emit({"event": "error", "message": str(exc)})


async def stream_events(task_id: str) -> AsyncIterator[str]:
    import json

    if task_id not in _tasks:
        yield 'data: {"event": "error", "message": "Task not found"}\n\n'
        return

    sent = 0
    while True:
        store = _tasks[task_id]
        events = store["events"]
        while sent < len(events):
            yield f"data: {json.dumps(events[sent], ensure_ascii=False)}\n\n"
            sent += 1

        if store["status"] in ("completed", "failed"):
            break

        await asyncio.sleep(0.5)


def get_result(task_id: str) -> dict | None:
    store = _tasks.get(task_id)
    if store is None:
        return None
    return store.get("result")
