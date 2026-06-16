# 페르소나 토론 파이프라인 라우터 — 7번 반응 산출 → 8~11 토론(mock) SSE 노출
#
# 현재 mock 엔진(wiring use_mock=True)으로 결정론 동작. 실 LLM·DB는 추후 wiring/영속화로 교체.
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction
from domain.simulation.service.debate_service import DebateService
from domain.simulation.tools.debate.loader import load_dummy_by_name
from domain.simulation.wiring import build_debate_service

router = APIRouter()

# 단일 store를 mock·LLM 서비스가 공유 — start는 서비스가 갈려도 stream/result는 run_id(store) 기반.
_store = InMemorySimulationStore()
_mock_service = build_debate_service(use_mock=True, store=_store)
_llm_service = build_debate_service(use_mock=False, store=_store)


def _svc(use_llm: bool) -> DebateService:
    """use_llm=True면 실 LLM(Haiku/GPT/Gemini+Opus), 아니면 mock(재현·무비용)."""
    return _llm_service if use_llm else _mock_service


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class DebateStartRequest(BaseModel):
    """토론 시작 입력 — 7번(반응 출력) 산출물. ad_analysis는 토론 주제 근거(선택)."""

    reactions: list[PersonaReaction]
    ad_analysis: AdInterpretation | None = None


@router.post("/start")
async def start_debate(body: DebateStartRequest, use_llm: bool = False) -> dict:
    """실제 반응 데이터로 토론 시작 — 비동기. use_llm=true면 실 LLM(비용 발생)."""
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    run_id = await _svc(use_llm).start(body.reactions, body.ad_analysis)
    return {"run_id": run_id, "stream_url": f"/api/debate/{run_id}/stream"}


@router.post("/dummy/{name}/start")
async def start_dummy_debate(name: str, use_llm: bool = False) -> dict:
    """더미(reaction-dummy1~5)로 토론 시작 — 데모/검증용. use_llm=true면 실 LLM(비용 발생)."""
    try:
        ds = load_dummy_by_name(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    run_id = await _svc(use_llm).start(ds.reactions, ds.ad_analysis)
    return {"run_id": run_id, "stream_url": f"/api/debate/{run_id}/stream"}


@router.get("/{run_id}/stream")
async def stream_debate(run_id: str) -> StreamingResponse:
    """SSE — 단계별 진행 이벤트(analysis→…→round_N→judge_final→report→completed)."""
    return StreamingResponse(
        _mock_service.stream_events(run_id),  # store 공유라 서비스 무관(run_id 기반)
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/{run_id}/result")
async def debate_result(run_id: str) -> dict:
    """완료된 토론 결과(analysis·aggregate·topic·panel·debate·report)."""
    result = _mock_service.get_result(run_id)  # store 공유라 서비스 무관
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 또는 토론 미완료")
    return result
