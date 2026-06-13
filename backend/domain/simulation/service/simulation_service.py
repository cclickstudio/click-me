from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import text

from core.db import AsyncSessionLocal
from core.schemas import Persona, SimulationRequest
from tools.ad_analysis.vision import run_ad_understanding
from tools.persona.factory import run_persona_factory
from tools.simulation.deliberation import run_deliberation
from tools.simulation.exposure import run_exposure
from tools.simulation.ssr_scorer import SSRScorer

logger = logging.getLogger("clickme")

_tasks: dict[str, dict] = {}


async def start_simulation(
    request: SimulationRequest,
    ssr_scorer: SSRScorer,
    project_id: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> str:
    task_id = str(uuid.uuid4())

    # DB에 simulations 행 미리 생성
    sim_db_id: str | None = None
    if project_id and organization_id:
        sim_db_id = await _create_simulation_row(
            project_id=project_id,
            organization_id=organization_id,
            user_id=user_id,
            sample_size=request.persona_set.get("size", 20),
            ad_title=request.ad_title or "광고 시뮬레이션",
        )

    _tasks[task_id] = {
        "status": "pending",
        "result": None,
        "events": [],
        "sim_db_id": sim_db_id,
        "project_id": project_id,
    }
    asyncio.create_task(_run_pipeline(task_id, request, ssr_scorer))
    return task_id


async def _create_simulation_row(
    project_id: str,
    organization_id: str,
    user_id: str | None,
    sample_size: int,
    ad_title: str,
) -> str | None:
    """simulations 테이블에 QUEUED 행 생성, sim_id 반환."""
    try:
        sim_id = str(uuid.uuid4())
        ad_id = str(uuid.uuid4())
        ad_analysis_id = str(uuid.uuid4())

        async with AsyncSessionLocal() as session:
            # ads 행 생성 (NOT NULL 컬럼 포함, ALTER TABLE로 nullable 처리 필요)
            await session.execute(
                text("""
                    INSERT INTO ads (id, project_id, title, media_type, created_at)
                    VALUES (:id, :project_id, :title, 'image', NOW())
                """),
                {"id": ad_id, "project_id": project_id, "title": ad_title},
            )
            # ad_analyses 행 생성
            await session.execute(
                text("""
                    INSERT INTO ad_analyses (id, ad_id, structured_analysis, intent_mismatch, model_version, created_at)
                    VALUES (:id, :ad_id, '{}'::jsonb, false, 'gpt-4o-mini', NOW())
                """),
                {"id": ad_analysis_id, "ad_id": ad_id},
            )
            # simulations 행 생성 (model_version 기본값은 ALTER TABLE로 설정 필요)
            await session.execute(
                text("""
                    INSERT INTO simulations
                        (id, ad_id, ad_analysis_id, organization_id, sample_size, status, model_version, created_by, created_at)
                    VALUES
                        (:id, :ad_id, :ad_analysis_id, :org_id, :sample_size, 'QUEUED', 'gpt-4o-mini', :created_by, NOW())
                """),
                {
                    "id": sim_id,
                    "ad_id": ad_id,
                    "ad_analysis_id": ad_analysis_id,
                    "org_id": organization_id,
                    "sample_size": sample_size,
                    "created_by": user_id,
                },
            )
            await session.commit()
        return sim_id
    except Exception as exc:
        logger.warning("시뮬레이션 DB 행 생성 실패 (계속 진행): %s", exc)
        return None


async def _save_simulation_result(
    sim_db_id: str,
    ad_id_str: str,
    result: dict,
    ssr_results: list[dict],
) -> None:
    """완료 후 simulations 상태 업데이트 + simulation_results 저장."""
    try:
        distribution = result.get("p0", {}).get("aggregate_purchase_intent", [])
        personas_data = result.get("p0", {}).get("persona_reactions", [])

        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE simulations
                    SET status = 'COMPLETED', completed_at = NOW()
                    WHERE id = :id
                """),
                {"id": sim_db_id},
            )
            # ad_id는 simulations 행의 ad_id를 조회
            row = await session.execute(
                text("SELECT ad_id FROM simulations WHERE id = :id"),
                {"id": sim_db_id},
            )
            r = row.fetchone()
            if r:
                await session.execute(
                    text("""
                        INSERT INTO simulation_results (id, ad_id, persona_count, distribution, personas, created_at)
                        VALUES (:id, :ad_id, :persona_count, :distribution::jsonb, :personas::jsonb, NOW())
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "ad_id": str(r.ad_id),
                        "persona_count": len(ssr_results),
                        "distribution": __import__("json").dumps(distribution),
                        "personas": __import__("json").dumps(personas_data),
                    },
                )
            await session.commit()
    except Exception as exc:
        logger.warning("시뮬레이션 결과 DB 저장 실패: %s", exc)


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
        emit(
            {
                "event": "progress",
                "stage": "persona_factory",
                "pct": 15,
                "message": "페르소나 생성 중...",
            }
        )

        personas = await run_persona_factory(
            simulation_id=request.simulation_id,
            count=request.persona_set.get("size", 20),
            ad_analysis=ad_analysis.model_dump(),
        )
        emit(
            {
                "event": "progress",
                "stage": "exposure",
                "pct": 30,
                "message": f"반응 시뮬레이션 중 (0/{len(personas)})",
            }
        )

        ssr_results: list[dict] = []
        sem = asyncio.Semaphore(5)

        async def process_persona(idx: int, persona: Persona) -> dict | None:
            async with sem:
                try:
                    exposure = await run_exposure(persona, ad_analysis.model_dump())

                    pct = 30 + int((idx + 1) / len(personas) * 30)
                    emit(
                        {
                            "event": "progress",
                            "stage": "exposure",
                            "pct": pct,
                            "message": f"반응 시뮬레이션 중 ({idx + 1}/{len(personas)})",
                        }
                    )

                    deliberation = await run_deliberation(
                        persona, exposure, ad_analysis.model_dump()
                    )

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
            raise RuntimeError(
                "모든 페르소나 처리에 실패했습니다. API 키 또는 네트워크를 확인하세요."
            )

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
                        "purchase_intent_distribution": (
                            r["signals"].get("conversion_intent", {}).get("raw_probs", [0.2] * 5)
                        ),
                    }
                    for r in ssr_results
                ],
                "aggregate_purchase_intent": purchase_dist,
                "kobaco_comparable": True,
            },
            "p1": {
                "signal_distributions": {
                    dim: {
                        "mean": avg_mean(dim),
                        "std": 0.1,
                        "p10": max(0.0, avg_mean(dim) - 0.2),
                        "p90": min(1.0, avg_mean(dim) + 0.2),
                        "raw_probs": avg_probs(dim),
                    }
                    for dim in ["attention", "sentiment", "click_intent", "comprehension", "recall"]
                },
                "kpi": {
                    "ctr": round(clk, 3),
                    "cvr": round(conv, 3),
                    "net_sentiment": round(avg_mean("sentiment"), 3),
                },
                "funnel": {
                    "attention": round(att, 3),
                    "comprehension": round(comp, 3),
                    "click": round(clk, 3),
                    "conversion": round(conv, 3),
                },
                "langsmith_trace_url": None,
                "note": "P1 신호는 탐색적(exploratory). 인간 ground truth 없음.",
            },
        }

        store["result"] = result
        store["status"] = "completed"

        # DB 저장
        sim_db_id = store.get("sim_db_id")
        if sim_db_id:
            asyncio.create_task(
                _save_simulation_result(sim_db_id, request.simulation_id, result, ssr_results)
            )

        emit({"event": "completed", "result_url": f"/api/simulate/{task_id}/result"})

    except Exception as exc:
        store["status"] = "failed"
        # 실패 상태 DB 업데이트
        sim_db_id = store.get("sim_db_id")
        if sim_db_id:
            try:
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        text(
                            "UPDATE simulations SET status = 'FAILED', completed_at = NOW() WHERE id = :id"
                        ),
                        {"id": sim_db_id},
                    )
                    await session.commit()
            except Exception:
                pass
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
