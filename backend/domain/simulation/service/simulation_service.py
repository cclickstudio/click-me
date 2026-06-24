# 시뮬레이션 오케스트레이션 서비스 — outer LangGraph 구동 + SSE 진행률
#
# _run 은 build_run_graph(P6) 컴파일본을 astream(updates)로 구동하며 노드별 진행률을 emit.
# 그래프 교체(mock ↔ 실 LLM)는 wiring.py 에서만. 결과 키는 분석팀 핸드오프 계약 유지.
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator

from core.tracing import make_trace_config
from domain.simulation.contracts.schemas import SimulationRunRequest
from domain.simulation.tools.aggregation.ocean_segments import ocean_segment_breakdown
from domain.simulation.tools.objective_fit import assess_objective_fit

logger = logging.getLogger("clickme")

# 반응 팬아웃 동시성 상한 — 과부하 엔드포인트에 1000콜을 한꺼번에 쏘지 않도록 제한(503 증폭 방지).
# LangGraph가 config.max_concurrency 로 Send fan-out 병렬 수를 제한한다. 환경변수로 튜닝 가능.
_MAX_REACTION_CONCURRENCY = int(os.getenv("SIMULATION_MAX_CONCURRENCY", "8"))


def _ad_block(request: SimulationRunRequest) -> dict:
    """ERD 광고 테이블 컬럼을 선언 입력(request)에서 인메모리 조립 — 폼에 없는 값은 None."""
    return {
        "ID": request.ad_id,
        "project_id": request.project_id,
        "title": request.ad_title,
        "media_type": "image" if request.ad_image_url else "text",
        "asset_url": request.ad_image_url,
        "copy_text": request.ad_content,
        "description": None,  # 폼 미수집
        "industry_category": None,  # 폼 미수집
        "product_category": request.product_category,
        "service_class": request.service_class,
        "ad_objective": request.ad_objective,
        "target_filter": request.target_filter,
        "status": "DRAFT",
    }


def _simulation_block(run_id, request, ad, reactions, aggregate, panel_version) -> dict:
    """ERD 시뮬레이션 테이블 컬럼을 실행 메타에서 인메모리 조립(DB 행 아님 — UUID는 미보유)."""
    return {
        "ID": run_id,
        "ad_id": request.ad_id,
        "ad_analysis_id": None,  # 영속화 시에만 생성
        "panel_id": panel_version,  # 인메모리엔 UUID 없음 → 패널 버전 문자열
        "organization_id": request.organization_id,
        "target_filter": request.target_filter,
        "target_mode": getattr(request.target_mode, "value", str(request.target_mode)),
        "sample_size": request.sample_size,
        "qa_passed_count": sum(1 for r in reactions if r.qa_passed),
        "low_sample_warning": aggregate.variance_warning,
        "status": "COMPLETED",
        "model_version": ad.model_version,
        "error_detail": None,
    }


class SimulationService:
    """주입된 outer 그래프를 구동. 그래프 구성·어댑터는 wiring.py 가 결정·주입한다."""

    def __init__(self, *, graph, store, persistence=None) -> None:
        self._graph = graph
        self._store = store
        self._persistence = persistence  # 주입되면 완료 런을 DB 저장(없으면 인메모리만)

    async def start(self, request: SimulationRunRequest) -> str:
        """비동기 시작 — 백그라운드 실행 후 run_id 반환(진행률은 SSE, 결과는 get_result)."""
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        asyncio.create_task(self._run(run_id, request))
        return run_id

    async def run(self, request: SimulationRunRequest) -> dict:
        """동기 실행 — 끝까지 돌린 뒤 결과(반응·루브릭·집계)를 한 번에 반환."""
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        await self._run(run_id, request)
        result = self._store.get_result(run_id)
        if result is None:
            events = self._store.get_events(run_id)
            msg = next(
                (e.get("message") for e in reversed(events) if e.get("event") == "error"), ""
            )
            raise RuntimeError(f"시뮬레이션 실패: {msg}")
        return result

    async def _run(self, run_id: str, request: SimulationRunRequest) -> None:
        store = self._store
        try:
            store.set_status(run_id, "RUNNING")
            store.emit(run_id, {"event": "progress", "stage": "ad_analysis", "pct": 5})

            state = {"request": request, "reactions": [], "personas": [], "rubric_scores": []}
            # LangSmith — 전체 시뮬레이션 = 요청 1건 = 최상위 Trace(simulation.simulate).
            # 페르소나 N명 반응은 이 Trace 아래 하위 Node로 자동 부채꼴 집계된다.
            trace_config = make_trace_config(
                domain="simulation",
                feature="simulate",
                ad_id=request.ad_id,
                project_id=request.project_id,
                extra_metadata={
                    "run_id": run_id,
                    "sample_size": request.sample_size,
                    "organization_id": request.organization_id,
                },
                extra_tags=["batch"] if request.sample_size > 10 else None,
            )
            # 반응 fan-out 병렬 수 제한(503 증폭 방지). preamble 노드는 단일이라 영향 없음.
            trace_config["max_concurrency"] = _MAX_REACTION_CONCURRENCY
            ad_dump: dict | None = None
            rubric_dump: list[dict] = []
            reactions: list[dict] = []
            aggregate_dump: dict | None = None
            # 영속화용 typed 객체(주입된 persistence 가 있을 때만 DB 저장에 사용)
            ad_obj = None
            personas: list = []
            rubric_objs: list = []
            reaction_objs: list = []
            aggregate_obj = None
            panel_version = "panel-v1"
            total = request.sample_size
            done = 0

            async for update in self._graph.astream(
                state, config=trace_config, stream_mode="updates"
            ):
                for node, out in update.items():
                    if not out:
                        continue
                    if node == "interpret_ad":
                        # 감지 + 의도 정합 채점을 함께 산출(§3.5-3) — ad·rubric_scores 동시 수집.
                        ad_obj = out["ad"]
                        ad_dump = ad_obj.model_dump()
                        rubric_objs = out.get("rubric_scores", [])
                        rubric_dump = [s.model_dump() for s in rubric_objs]
                        store.emit(run_id, {"event": "progress", "stage": "panel", "pct": 15})
                    elif node == "load_panel":
                        personas = out["personas"]
                        panel_version = out.get("panel_version") or panel_version
                        total = len(personas) or total
                        store.emit(run_id, {"event": "progress", "stage": "reaction", "pct": 30})
                    elif node == "react":
                        for r in out.get("reactions", []):
                            reaction_objs.append(r)
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
                        aggregate_obj = out["aggregate"]
                        aggregate_dump = aggregate_obj.model_dump()  # 집계 계약

            if not reactions:
                raise RuntimeError("모든 페르소나 반응 생성에 실패했습니다.")

            result = {
                "run_id": run_id,
                "ad": _ad_block(request),  # 광고(선언 입력) 테이블
                "ad_analysis": ad_dump,  # 광고해석 테이블
                "simulation": _simulation_block(  # 시뮬레이션(실행 메타) 테이블
                    run_id, request, ad_obj, reaction_objs, aggregate_obj, panel_version
                ),
                "personas": [p.model_dump() for p in personas],  # 반응별 페르소나 속성 조회용
                "reactions": reactions,
                "rubric_scores": rubric_dump,
                "aggregate": aggregate_dump,
                # OCEAN 성향별 반응 분해(결과 해석) — 연령×성별 외 '성격 축'. 빈 입력이면 빈 구조.
                "ocean_segments": ocean_segment_breakdown(personas, reaction_objs),
                # 상세 페이지 표시용 — 업로드 시 presigned URL, 외부 URL이면 그대로, 로컬폴백이면 경로.
                "ad_asset_url": request.ad_image_url,
            }
            # 캠페인 목표 달성 가능성(결정론 룰) — 목표 선언 + 집계가 있을 때만(exploratory).
            if request.ad_objective and aggregate_obj is not None:
                fit = assess_objective_fit(request.ad_objective, aggregate_obj, reaction_objs)
                result["objective_fit"] = fit.model_dump() if fit is not None else None
            # DB 영속화 — 프로젝트 선택 시에만(ads→projects FK). 실패해도 런 결과(인메모리)는 유지.
            if (
                self._persistence is not None
                and ad_obj is not None
                and aggregate_obj is not None
                and request.project_id
            ):
                try:
                    sim_id = await self._persistence.save_completed_run(
                        request=request,
                        ad=ad_obj,
                        personas=personas,
                        reactions=reaction_objs,
                        rubric=rubric_objs,
                        aggregate=aggregate_obj,
                        panel_version=panel_version,
                    )
                    result["simulation_id"] = str(sim_id)
                except Exception:
                    logger.exception("영속화 실패(런은 유지) run_id=%s", run_id)

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
