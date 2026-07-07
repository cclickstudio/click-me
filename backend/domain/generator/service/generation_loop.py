# 생성 자동 개선 루프 — QA 품질점수 기반으로 생성→평가→개선을 반복(결정론 제어 + LLM 판단 1지점)
"""구조화 루프 모듈. 채팅 에이전트(CLIO)가 위임 도구 1개로 호출하고, 반복의 내부 트레이스는
여기 격리한다. 루프 제어(반복 상한·임계 판정·best 선택·조기중단)는 결정론, 개선방향 도출만 LLM.

기존 생성과 동일하게 백그라운드 태스크 + SSE 스트림으로 돌린다(generator_service 패턴 미러링).
평가 신호는 QA 품질점수(quality_score)만 사용한다(시뮬레이션 미사용, 저비용).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.pipeline.improvement_guide import classify_improvements
from domain.generator.service import generator_service
from domain.generator.service.generator_service import _QA_STRENGTH_LABELS

logger = logging.getLogger("clickme")

# 루프 태스크 저장소 — generator_service._tasks 와 동일 패턴(프로세스 메모리, 재시작 시 초기화).
_loops: dict[str, dict] = {}

_DEFAULT_TARGET = 0.8
_DEFAULT_MAX_ITERS = 3
_AWAIT_TIMEOUT = 600.0  # 생성 1회 완료 대기 상한(초)

_DERIVE_FIX_SYSTEM = (
    "너는 광고 개선 코치다. 아래 광고 카피와 품질 약점을 보고, 이미지·카피 재생성으로 바로 반영할 "
    "구체적 개선 방향을 2~4개의 한국어 불릿으로 제시하라. 추상적 지시(예: '품질을 높여라')는 금지하고, "
    "무엇을 어떻게 바꿀지 구체적으로 적는다. 문장 끝에 콜론을 쓰지 않는다."
)

# 최초 1회 시뮬(eval_mode=simulation)에서 최저 KPI 축을 고르는 목표선 — 내부 방향 신호 전용
# (실측 스케일 환산 아님, 반복 간 비교 아님). 목표선 미달 폭을 정규화해 가장 심한 축을 고른다.
_KPI_TARGETS = {
    "click": ("click_intent_rate", 0.25, 0.25),  # (KPI키, 목표, 정규화 분모)
    "purchase": ("purchase_intent", 3.5, 2.5),
    "trust": ("trust_avg", 3.5, 2.5),
}
_REJECTION_TARGET = 0.30  # 거부율은 높을수록 나쁨(별도 처리)

# 최저 축 → KB(ad_image_guide.md) 개선 패턴 섹션 검색 쿼리
_KPI_KB_QUERY = {
    "click": "클릭 의향률이 낮을 때 개선 패턴",
    "purchase": "구매의도가 낮을 때 개선 패턴",
    "rejection": "거부율이 높을 때 개선 패턴",
    "trust": "신뢰도가 낮을 때 개선 패턴",
}
_KPI_DIAG_LABEL = {
    "click": "클릭 의향률",
    "purchase": "구매의도",
    "rejection": "거부율",
    "trust": "신뢰도",
}


def _create_req(seed: dict, project_id: str | None) -> GenerationCreateRequest:
    return GenerationCreateRequest(
        mode=GenerationMode.CREATE,
        project_id=project_id,
        product_name=seed.get("product_name", ""),
        product_description=seed.get("product_description", ""),
        target_audience=seed.get("target_audience", ""),
        campaign_objective=seed.get("campaign_objective") or "conversion",
    )


def _improve_req(
    seed: dict, best: dict, fix: str, weakness: str, project_id: str | None
) -> GenerationCreateRequest:
    # IMPROVE 필수 필드: simulation_summary(existing_ad_s3_key는 참고용 힌트). 시뮬 미사용이므로 QA 약점 요약을
    # simulation_summary에 담는다(스키마 재사용, 후속에서 evaluation_summary로 일반화 가능).
    return GenerationCreateRequest(
        mode=GenerationMode.IMPROVE,
        project_id=project_id,
        existing_ad_s3_key=best.get("s3_key"),
        simulation_summary=weakness or "품질 개선 필요",
        fix_requests=fix,
        product_name=seed.get("product_name", ""),
        product_description=seed.get("product_description", ""),
        target_audience=seed.get("target_audience", ""),
        campaign_objective=seed.get("campaign_objective") or "conversion",
    )


def _best_of(detail: dict | None) -> dict | None:
    """get_detail 결과에서 최고 후보(랭크 1) 반환 — get_detail이 이미 quality_score순 정렬."""
    if not detail:
        return None
    cands = detail.get("candidates") or []
    return cands[0] if cands else None


def _qa_weakness_summary(candidate: dict) -> str:
    """후보 QA에서 점수 낮은 체크(약점)를 한 줄 요약으로. 없으면 빈 문자열."""
    qa = candidate.get("qa_result") or {}
    weak = [
        (k, float(v.get("score") or 0.0))
        for k, v in qa.items()
        if isinstance(v, dict) and "score" in v and (v.get("score") or 0.0) < 1.0
    ]
    if not weak:
        return ""
    weak.sort(key=lambda kv: kv[1])
    parts = [f"{_QA_STRENGTH_LABELS.get(k, k)}({score:.2f})" for k, score in weak]
    return "품질 약점: " + ", ".join(parts)


async def _await_completion(
    generation_id: str, timeout: float = _AWAIT_TIMEOUT, interval: float = 1.0
) -> None:
    """생성 백그라운드 태스크가 완료/실패할 때까지 대기(같은 이벤트루프의 파이프라인이 진행)."""
    waited = 0.0
    while waited < timeout:
        status = (generator_service._tasks.get(generation_id) or {}).get("status")
        if status in ("completed", "failed"):
            return
        await asyncio.sleep(interval)
        waited += interval


def _weakest_kpi_axis(kpis: dict) -> tuple[str, str] | None:
    """4대 KPI 중 목표선 미달이 가장 심한 축 → (axis_key, 한줄 진단). 문제 없으면 None."""
    scored: list[tuple[str, float, str]] = []
    for axis, (key, target, denom) in _KPI_TARGETS.items():
        v = kpis.get(key)
        if v is not None and v < target:
            severity = (target - v) / denom
            label = (
                f"클릭의향 {round(v * 100)}%"
                if axis == "click"
                else f"{_KPI_DIAG_LABEL[axis]} {v:.1f}/5"
            )
            scored.append((axis, severity, label))
    rj = kpis.get("rejection_rate")
    if rj is not None and rj >= _REJECTION_TARGET:
        scored.append(("rejection", (rj - _REJECTION_TARGET) / 0.70, f"거부율 {round(rj * 100)}%"))
    if not scored:
        return None
    axis, _, label = max(scored, key=lambda s: s[1])
    return axis, label


async def _derive_sim_seed(kpis: dict) -> tuple[str, str]:
    """최초 시뮬 KPI → (개선 시드 문자열, 진단 라벨). KB 개선 패턴을 근거로 붙인다.

    시드는 개선 반복 전체에 고정 주입되는 '소비자 반응 기반 방향'(하이브리드 B). 문제 없으면 빈 문자열.
    """
    axis = _weakest_kpi_axis(kpis)
    if axis is None:
        return "", ""
    axis_key, diag = axis
    patterns = ""
    try:  # KB 미적재·키 없음은 조용히 폴백(진단 라벨만으로 진행)
        from core.config import settings  # noqa: PLC0415
        from domain.generator.assistant.retriever import GenKbRetriever  # noqa: PLC0415

        api_key = getattr(settings, "openai_api_key", None)
        if api_key and not getattr(settings, "use_mock", True):
            hits = await GenKbRetriever(api_key=api_key).search(_KPI_KB_QUERY[axis_key], k=1)
            if hits:
                patterns = hits[0]["chunk"]
    except Exception:  # noqa: BLE001
        patterns = ""
    seed = f"소비자 반응 진단(최초 시뮬 1회) — 최우선 개선 지표: {diag}."
    if patterns:
        seed += f"\n[개선 패턴 참조]\n{patterns}"
    return seed, diag


async def _derive_fix(candidate: dict, seed: dict, sim_seed: str = "") -> str:
    """유일한 LLM 판단 — QA 약점+카피(+최초 시뮬 시드)를 읽고 구체 개선방향 도출 → 이미지 반영 필터.

    classify_improvements(개선점 분류기)로 이미지 반영 지시문만 추려 fix_requests 문자열로 만든다.
    sim_seed는 최초 시뮬로 얻은 소비자 반응 방향으로, 있으면 모든 반복에 고정 주입된다.
    """
    from domain.generator.llm.factory import build_text_llm, with_llm_retry  # noqa: PLC0415

    weakness = _qa_weakness_summary(candidate)
    copy = candidate.get("copy") or {}
    seed_block = f"\n소비자 반응 방향(우선 반영): {sim_seed}" if sim_seed else ""
    user = (
        f"상품: {seed.get('product_name', '')} / 타깃: {seed.get('target_audience', '')}\n"
        f"현재 카피 — 헤드라인 '{copy.get('headline', '')}' / 본문 '{copy.get('body', '')}' / "
        f"CTA '{copy.get('cta', '')}'\n{weakness or '두드러진 약점 없음 — 소구·가독성을 더 강화'}"
        f"{seed_block}"
    )
    llm = with_llm_retry(build_text_llm(temperature=0.3, max_tokens=400))
    resp = await llm.ainvoke([("system", _DERIVE_FIX_SYSTEM), ("user", user)])
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    classification = await classify_improvements(
        simulation_summary=sim_seed or None,
        plain_summary=None,
        improvement_direction=None,
        fix_requests=raw,
    )
    if classification.directives:
        return "\n".join(f"- {a}" for a in classification.directives)
    return raw.strip()


def _history_entry(iteration: int, generation_id: str, candidate: dict) -> dict:
    return {
        "iteration": iteration,
        "generation_id": generation_id,
        "candidate_id": candidate.get("candidate_id"),
        "quality_score": candidate.get("quality_score"),
        "performance_summary": candidate.get("performance_summary"),
    }


async def run_generation_loop(
    seed: dict,
    quality_target: float = _DEFAULT_TARGET,
    max_iterations: int = _DEFAULT_MAX_ITERS,
    project_id: str | None = None,
    created_by: uuid.UUID | None = None,
    emit: Callable[[dict], None] | None = None,
    simulate_fn: Callable[[dict, dict], Awaitable[dict | None]] | None = None,
) -> dict:
    """생성→평가→개선 루프(결정론). 반환: final_generation_id·best_candidate·threshold_met·iterations·history.

    simulate_fn이 있으면(eval_mode=simulation) iteration 0 시안에 1회 시뮬을 돌려, 최저 KPI 축
    기반 개선 방향(sim_seed)을 얻어 모든 개선 반복에 고정 주입한다(하이브리드 B). 시뮬 실패는
    조용히 QA-only로 폴백한다.
    """
    _emit = emit or (lambda _e: None)

    # ── iteration 0: 최초 생성 ──
    _emit({"event": "iteration_start", "iteration": 0, "mode": "create"})
    gid = await generator_service.start_generation(
        _create_req(seed, project_id), created_by=created_by
    )
    await _await_completion(gid)
    best = _best_of(await generator_service.get_detail(gid))
    if best is None:
        _emit({"event": "error", "iteration": 0, "message": "생성 실패 또는 후보 없음"})
        return {
            "final_generation_id": gid,
            "best_candidate": None,
            "threshold_met": False,
            "iterations": 0,
            "history": [],
        }
    best_gid = gid
    history = [_history_entry(0, gid, best)]
    _emit(
        {
            "event": "generated",
            "iteration": 0,
            "generation_id": gid,
            "quality_score": best["quality_score"],
        }
    )

    # ── 최초 1회 시뮬(옵션) → 소비자 반응 기반 개선 시드 확정 ──
    sim_seed = ""
    if simulate_fn is not None:
        kpis = None
        try:
            kpis = await simulate_fn(best, seed)
        except Exception:  # noqa: BLE001 — 시뮬 실패는 QA-only 폴백
            kpis = None
        if kpis:
            _emit({"event": "simulated", "iteration": 0, "kpis": kpis})
            sim_seed, diag = await _derive_sim_seed(kpis)
            if sim_seed:
                _emit({"event": "sim_direction", "iteration": 0, "focus": diag})

    # ── 개선 반복(임계 미달 & 상한 내) ──
    it = 0
    while (best.get("quality_score") or 0.0) < quality_target and it < max_iterations:
        it += 1
        fix = await _derive_fix(best, seed, sim_seed=sim_seed)
        if not fix:
            _emit({"event": "stopped", "iteration": it, "reason": "no_actionable_fix"})
            break
        weakness = _qa_weakness_summary(best)
        _emit({"event": "improving", "iteration": it, "fix": fix})
        gid = await generator_service.start_generation(
            _improve_req(seed, best, fix, weakness, project_id), created_by=created_by
        )
        await _await_completion(gid)
        cand = _best_of(await generator_service.get_detail(gid))
        if cand is None:
            _emit({"event": "error", "iteration": it, "message": "개선 생성 실패"})
            break
        history.append(_history_entry(it, gid, cand))
        _emit(
            {
                "event": "generated",
                "iteration": it,
                "generation_id": gid,
                "quality_score": cand["quality_score"],
            }
        )
        # 세대 간 best 유지 — 개선본이 더 좋거나 같으면 교체.
        if (cand.get("quality_score") or 0.0) >= (best.get("quality_score") or 0.0):
            best, best_gid = cand, gid

    threshold_met = (best.get("quality_score") or 0.0) >= quality_target
    result = {
        "final_generation_id": best_gid,
        "best_candidate": best,
        "threshold_met": threshold_met,
        "iterations": it,
        "history": history,
    }
    _emit(
        {
            "event": "completed",
            "final_generation_id": best_gid,
            "best_candidate_id": best.get("candidate_id"),
            "quality_score": best.get("quality_score"),
            "threshold_met": threshold_met,
            "iterations": it,
        }
    )
    return result


async def start_loop(
    seed: dict,
    quality_target: float = _DEFAULT_TARGET,
    max_iterations: int = _DEFAULT_MAX_ITERS,
    project_id: str | None = None,
    created_by: uuid.UUID | None = None,
    simulate_fn: Callable[[dict, dict], Awaitable[dict | None]] | None = None,
) -> str:
    """루프를 백그라운드로 시작하고 loop_id를 반환한다(generator_service.start_generation 패턴).

    simulate_fn을 주면 최초 1회 시뮬 기반 개선(eval_mode=simulation) — 조립은 호출부(api/assistant).
    """
    loop_id = str(uuid.uuid4())
    store: dict = {"status": "running", "events": [], "result": None}
    _loops[loop_id] = store

    def emit(event: dict) -> None:
        store["events"].append(event)

    async def _run() -> None:
        try:
            store["result"] = await run_generation_loop(
                seed,
                quality_target,
                max_iterations,
                project_id,
                created_by,
                emit,
                simulate_fn=simulate_fn,
            )
            store["status"] = "completed"
        except Exception as exc:  # noqa: BLE001 — 실패도 스트림으로 알리고 상태 종결
            logger.exception("생성 개선 루프 실패: loop_id=%s", loop_id)
            store["status"] = "failed"
            emit({"event": "error", "message": str(exc)})

    asyncio.create_task(_run())
    return loop_id


async def stream_loop_events(loop_id: str) -> AsyncIterator[str]:
    """루프 진행 SSE — generator_service.stream_events 와 동일 방식."""
    if loop_id not in _loops:
        yield 'data: {"event": "error", "message": "loop not found"}\n\n'
        return
    sent = 0
    while True:
        store = _loops[loop_id]
        events = store["events"]
        while sent < len(events):
            yield f"data: {json.dumps(events[sent], ensure_ascii=False)}\n\n"
            sent += 1
        if store["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)


def get_loop_result(loop_id: str) -> dict | None:
    """루프 상태·최종 결과. 없으면 None."""
    store = _loops.get(loop_id)
    if store is None:
        return None
    return {"loop_id": loop_id, "status": store["status"], "result": store["result"]}
