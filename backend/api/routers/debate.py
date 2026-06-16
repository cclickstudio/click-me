# 페르소나 토론 파이프라인 라우터 — 7번 반응 산출 → 8~11 토론(mock) SSE 노출
#
# 현재 mock 엔진(wiring use_mock=True)으로 결정론 동작. 실 LLM·DB는 추후 wiring/영속화로 교체.
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction
from domain.simulation.tools.debate.loader import load_dummy_by_name
from domain.simulation.wiring import build_debate_service

router = APIRouter()

# 토론 서비스 싱글톤 — start/stream/result가 같은 store를 공유해야 하므로 모듈 레벨 1개.
_service = build_debate_service(use_mock=True)

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class DebateStartRequest(BaseModel):
    """토론 시작 입력 — 7번(반응 출력) 산출물. ad_analysis는 토론 주제 근거(선택)."""

    reactions: list[PersonaReaction]
    ad_analysis: AdInterpretation | None = None


@router.post("/start")
async def start_debate(body: DebateStartRequest) -> dict:
    """실제 반응 데이터로 토론 시작 — 비동기, run_id·stream_url 반환."""
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    run_id = await _service.start(body.reactions, body.ad_analysis)
    return {"run_id": run_id, "stream_url": f"/api/debate/{run_id}/stream"}


@router.post("/dummy/{name}/start")
async def start_dummy_debate(name: str) -> dict:
    """더미(reaction-dummy1~5)로 토론 시작 — 데모/검증용."""
    try:
        ds = load_dummy_by_name(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    run_id = await _service.start(ds.reactions, ds.ad_analysis)
    return {"run_id": run_id, "stream_url": f"/api/debate/{run_id}/stream"}


@router.get("/{run_id}/stream")
async def stream_debate(run_id: str) -> StreamingResponse:
    """SSE — 단계별 진행 이벤트(analysis→…→round_N→judge_final→report→completed)."""
    return StreamingResponse(
        _service.stream_events(run_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/{run_id}/result")
async def debate_result(run_id: str) -> dict:
    """완료된 토론 결과(analysis·aggregate·topic·panel·debate·report)."""
    result = _service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 또는 토론 미완료")
    return result
