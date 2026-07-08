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

from core.center_suggestions import create_center_suggestion
from core.config import settings
from core.execution_log import record_execution
from core.tracing import make_trace_config
from domain.management.contracts.policy import exec_gate_thresholds, is_executable_verdict
from domain.simulation.adapters.ad_image_store import proxy_url_for
from domain.simulation.contracts.schemas import SegmentSpec, SimulationRunRequest
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


async def _record_run_history(request: SimulationRunRequest, result: dict) -> None:
    """완료 런 1건을 실행 히스토리(롱텀 메모리)에 적재 — UI·직접 API 실행분 회수용.

    채팅 요청행(spawn_persist)과는 payload.stage="completed"로 구분(요청/완료 2행 패턴).
    project_id 없으면 record_execution이 생략, 실패도 조용히 무시(best-effort·비차단).
    """
    agg = result.get("aggregate") or {}
    click_pct = round(float(agg.get("click_intent_rate") or 0) * 100, 1)
    reject_pct = round(float(agg.get("rejection_rate") or 0) * 100, 1)
    await record_execution(
        request.project_id,
        "simulation",
        "run_simulation",
        f"시뮬레이션 완료 — {request.ad_title} 표본 {request.sample_size}명 "
        f"클릭 의향률 {click_pct}% 거부율 {reject_pct}%",
        payload={
            "stage": "completed",
            "run_id": result.get("run_id"),
            "simulation_id": result.get("simulation_id"),
            "ad_title": request.ad_title,
            "sample_size": request.sample_size,
            "click_intent_rate": agg.get("click_intent_rate"),
            "purchase_intent": agg.get("purchase_intent"),
            "trust_avg": agg.get("trust_avg"),
            "rejection_rate": agg.get("rejection_rate"),
        },
        user_id=request.user_id,
    )


async def _record_gen_suggestion(request: SimulationRunRequest, result: dict) -> None:
    """시뮬 완료 직후 "제너레이터 제안"(gen_suggest) 센터 알림을 인라인 생성 — 스펙 §5.2.

    상세(개선안)는 프론트가 source_sim_id로 GET /api/chat/result-summary?kind=sim 재조회.
    영속화된 런(simulation_id 존재)에서만 — 프로젝트 미선택 런은 귀속할 곳이 없어 생략.
    best-effort·비차단(create_center_suggestion 내부에서 예외 흡수).
    """
    sim_id = result.get("simulation_id")
    if not sim_id or not request.project_id:
        return
    agg = result.get("aggregate") or {}
    await create_center_suggestion(
        suggestion_type="gen_suggest",
        organization_id=request.organization_id,
        project_id=request.project_id,
        reason="simulation_improvement",
        source_sim_id=sim_id,
        payload={
            "title": "제너레이터 제안",
            "message": "시뮬 결과에 맞춘 개선 시안을 생성해 보시겠어요?",
            "ad_title": request.ad_title,
            "kpi": {
                "click_intent_rate": agg.get("click_intent_rate"),
                "purchase_intent": agg.get("purchase_intent"),
                "trust_avg": agg.get("trust_avg"),
                "rejection_rate": agg.get("rejection_rate"),
            },
        },
        dedup_key=f"gen_suggest:{sim_id}",
    )


async def _record_launch_suggestion(request: SimulationRunRequest, result: dict) -> None:
    """집행 권장 게이트 통과 시 "집행 제안"(launch_suggest) 센터 알림을 인라인 생성.

    판정 정본은 management 집행 게이트(contracts.policy 재사용, 스펙 2026-07-07 §5) —
    알림 받은 건은 from-simulation 집행 게이트를 반드시 통과한다(409 UX 파탄 방지).
    영속화된 런(simulation_id 존재)에서만. best-effort·비차단(gen_suggest와 동일).
    """
    sim_id = result.get("simulation_id")
    if not sim_id or not request.project_id:
        return
    agg = result.get("aggregate") or {}
    cir = float(agg.get("click_intent_rate") or 0.0)
    rej = float(agg.get("rejection_rate") or 0.0)
    min_cir, max_rej = exec_gate_thresholds(settings)
    if not is_executable_verdict(cir, rej, min_cir=min_cir, max_rej=max_rej):
        return
    await create_center_suggestion(
        suggestion_type="launch_suggest",
        organization_id=request.organization_id,
        project_id=request.project_id,
        reason="sim_result_good",
        source_sim_id=sim_id,
        payload={
            "title": "집행 제안",
            "message": "시뮬 결과가 집행 권장 기준을 충족했어요. 이 광고로 캠페인 집행을 검토해 보세요.",
            "ad_title": request.ad_title,
            "click_intent_rate": cir,
            "rejection_rate": rej,
        },
        dedup_key=f"launch_suggest:{sim_id}",
    )


async def _record_comparison_history(
    request: SimulationRunRequest, run_id: str, segments: list[SegmentSpec]
) -> None:
    """persona_set 비교 런 1건을 실행 히스토리에 적재(1런=1행) — 세그먼트 라벨로 회수."""
    labels = [seg.label for seg in segments]
    await record_execution(
        request.project_id,
        "simulation",
        "run_comparison",
        f"페르소나 비교 시뮬레이션 완료 — {request.ad_title} "
        f"세그먼트 {len(segments)}개({', '.join(labels)})",
        payload={
            "stage": "completed",
            "run_id": run_id,
            "mode": "persona_set",
            "ad_title": request.ad_title,
            "segment_labels": labels,
        },
        user_id=request.user_id,
    )


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

    async def start_comparison(
        self, request: SimulationRunRequest, segments: list[SegmentSpec]
    ) -> str:
        """persona_set 비동기 시작 — 세그먼트 배열을 순차 개별 실행. run_id 반환(진행률 SSE)."""
        run_id = str(uuid.uuid4())
        self._store.create_run(run_id)
        asyncio.create_task(self._run_comparison(run_id, request, segments))
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
        """synthetic·individual 단일 런 — 코어 파이프라인을 돌려 결과를 저장(응답 구조 무변경)."""
        store = self._store
        try:
            store.set_status(run_id, "RUNNING")
            result = await self._produce_result(request, run_id=run_id)
            store.set_result(run_id, result)
            store.set_status(run_id, "COMPLETED")
            store.emit(
                run_id, {"event": "completed", "result_url": f"/api/simulate/{run_id}/result"}
            )
            # 실행 확정 지점 롱텀(실행 히스토리) 적재 — UI·채팅 모든 경로가 여기로 수렴.
            await _record_run_history(request, result)
            # 센터 제안 알림 — 시뮬 완료 → "제너레이터 제안" 인라인 생성(best-effort).
            await _record_gen_suggestion(request, result)
            # 집행 제안 — 집행 권장 게이트 통과 시에만 생성(정본: management contracts.policy).
            await _record_launch_suggestion(request, result)
        except Exception as exc:
            store.set_status(run_id, "FAILED")
            store.emit(run_id, {"event": "error", "message": str(exc)})
            logger.exception("시뮬레이션 실패 run_id=%s", run_id)

    async def _run_comparison(
        self, run_id: str, request: SimulationRunRequest, segments: list[SegmentSpec]
    ) -> None:
        """persona_set 런 — 세그먼트마다 코어 파이프라인을 개별 실행해 SimComparisonResult로 조립.

        진행률은 세그먼트 메타(segment_label·segment_index·segment_total)를 얹어 하나의 compare
        run_id로 스트리밍한다. 동시성 증폭을 피하려 세그먼트는 순차 실행(각 세그먼트 내부 반응은
        기존 _MAX_REACTION_CONCURRENCY로 팬아웃). 세그먼트별 DB 영속화는 각자 고유 persist_id로
        저장돼 PK(run_id 통일) 충돌을 피한다.
        """
        store = self._store
        try:
            store.set_status(run_id, "RUNNING")
            total = len(segments)
            seg_payloads: list[dict] = []
            for idx, seg in enumerate(segments):
                # 세그먼트별 요청 — 공통 광고 필드는 유지, 타깃/표본만 세그먼트 값으로 교체.
                # analysis_mode는 synthetic으로 내려 각 세그먼트를 일반 런과 동일하게 돌린다.
                seg_request = request.model_copy(
                    update={
                        "target_filter": seg.target_filter,
                        "sample_size": seg.sample_size,
                        "analysis_mode": "synthetic",
                    }
                )
                seg_meta = {
                    "segment_label": seg.label,
                    "segment_index": idx,
                    "segment_total": total,
                }
                # 세그먼트마다 고유 persist_id — DB PK는 run_id와 통일돼 있어(공유 시 충돌) 분리 필수.
                seg_persist_id = str(uuid.uuid4())
                seg_result = await self._produce_result(
                    seg_request,
                    run_id=seg_persist_id,
                    emit_run_id=run_id,
                    segment_meta=seg_meta,
                )
                seg_payloads.append(
                    {
                        "label": seg.label,
                        "target_filter": seg.target_filter,
                        "sample_size": seg.sample_size,
                        "result": seg_result,
                    }
                )
            comparison = {"mode": "persona_set", "run_id": run_id, "segments": seg_payloads}
            store.set_result(run_id, comparison)
            store.set_status(run_id, "COMPLETED")
            store.emit(
                run_id, {"event": "completed", "result_url": f"/api/simulation/{run_id}/result"}
            )
            # 비교 런도 실행 확정 지점에서 롱텀 적재(1런=1행, 세그먼트 개별행 아님).
            await _record_comparison_history(request, run_id, segments)
        except Exception as exc:
            store.set_status(run_id, "FAILED")
            store.emit(run_id, {"event": "error", "message": str(exc)})
            logger.exception("persona_set 시뮬레이션 실패 run_id=%s", run_id)

    async def _produce_result(
        self,
        request: SimulationRunRequest,
        *,
        run_id: str,
        emit_run_id: str | None = None,
        segment_meta: dict | None = None,
    ) -> dict:
        """코어 파이프라인 — outer 그래프를 돌려 결과 dict를 조립·반환(상태/완료 이벤트는 호출자).

        run_id: 결과 식별·DB 영속 PK. emit_run_id: SSE 진행률을 보낼 run(기본 run_id).
        segment_meta: persona_set에서 진행률 이벤트에 얹을 세그먼트 정보(synthetic은 None → 무변경).
        """
        store = self._store
        eid = emit_run_id or run_id

        def _emit(event: dict) -> None:
            store.emit(eid, {**event, **segment_meta} if segment_meta else event)

        _emit({"event": "progress", "stage": "ad_analysis", "pct": 5})

        state = {"request": request, "reactions": [], "personas": [], "rubric_scores": []}
        # LangSmith — 전체 시뮬레이션 = 요청 1건 = 최상위 Trace(simulation.simulate).
        # 페르소나 N명 반응은 이 Trace 아래 하위 Node로 자동 부채꼴 집계된다.
        trace_config = make_trace_config(
            domain="simulation",
            feature="simulate",
            user_id=request.user_id or "anonymous",
            login_id=request.login_id,
            user_name=request.user_name,
            role=request.role,
            ad_id=request.ad_id,
            project_id=request.project_id,
            extra_metadata={
                "run_id": run_id,
                "sample_size": request.sample_size,
                "organization_id": request.organization_id,
            },
            extra_tags=["batch"] if request.sample_size > 10 else None,
        )
        # run_name은 make_trace_config 표준(simulation.simulate)을 그대로 사용.
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

        async for update in self._graph.astream(state, config=trace_config, stream_mode="updates"):
            for node, out in update.items():
                if not out:
                    continue
                if node == "interpret_ad":
                    # 감지 + 의도 정합 채점을 함께 산출(§3.5-3) — ad·rubric_scores 동시 수집.
                    ad_obj = out["ad"]
                    ad_dump = ad_obj.model_dump()
                    rubric_objs = out.get("rubric_scores", [])
                    rubric_dump = [s.model_dump() for s in rubric_objs]
                    _emit({"event": "progress", "stage": "panel", "pct": 15})
                elif node == "load_panel":
                    personas = out["personas"]
                    panel_version = out.get("panel_version") or panel_version
                    total = len(personas) or total
                    _emit({"event": "progress", "stage": "reaction", "pct": 30})
                elif node == "react":
                    for r in out.get("reactions", []):
                        reaction_objs.append(r)
                        reactions.append(r.model_dump())  # §3.5 계약 (분석팀 입력)
                        done += 1
                        pct = 30 + int(done / total * 50) if total else 80
                        _emit(
                            {
                                "event": "progress",
                                "stage": "reaction",
                                "pct": pct,
                                "message": f"반응 {done}/{total}",
                            }
                        )
                elif node == "aggregate":
                    _emit({"event": "milestone", "stage": "aggregate", "pct": 95})
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
            # 상세 페이지 표시용 — S3 키는 프록시 URL로(자격증명 노출 방지), 외부 URL은 그대로.
            "ad_asset_url": proxy_url_for(request.ad_image_key or request.ad_image_url),
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
                    simulation_id=uuid.UUID(run_id),  # DB PK=run_id 통일 → 챗 즉시 조회
                )
                result["simulation_id"] = str(sim_id)
                # 성과 비교 자동 연결 — fromCampaign 경로 진입 시 서버에서 직접 링크.
                if request.from_campaign_id and request.organization_id:
                    try:
                        await self._persistence.link_to_campaign(
                            sim_id,
                            request.from_campaign_id,
                            request.organization_id,
                        )
                        logger.info(
                            "campaign 자동 링크 완료 sim=%s campaign=%s",
                            sim_id,
                            request.from_campaign_id,
                        )
                    except Exception:
                        logger.exception(
                            "campaign 링크 실패(런은 유지) sim=%s campaign=%s",
                            sim_id,
                            request.from_campaign_id,
                        )
            except Exception:
                logger.exception("영속화 실패(런은 유지) run_id=%s", run_id)

        return result

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

    def get_run_status(self, run_id: str) -> dict | None:
        """진행 상태 — 새로고침 후 백그라운드 런 복원용. 모르는 run이면 None(서버 재시작·완료소실)."""
        status = self._store.get_status(run_id)
        if status is None:
            return None
        pct, stage = 0, None
        for ev in self._store.get_events(run_id):
            if isinstance(ev.get("pct"), int):
                pct = ev["pct"]
            if ev.get("stage"):
                stage = ev["stage"]
        return {"run_id": run_id, "status": status, "pct": pct, "stage": stage}
