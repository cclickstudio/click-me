# 페르소나 토론 파이프라인 라우터 — 7번 반응 산출(JSON) → 8·9 분석 / 8~11 토론(SSE)
#
# 입력은 JSON body(reactions[])로 통일. 분석(analyze)은 동기 즉시 반환, 토론(start)은 SSE 비동기.
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.contracts.schemas import AdInterpretation, Persona, PersonaReaction
from domain.simulation.service.debate_service import DebateService
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


class DebateRequest(BaseModel):
    """토론/분석 입력 — 7번(반응 출력) 산출물. reactions 필수, 나머지 선택.

    더미·시뮬레이션 결과 JSON 전체를 그대로 붙여넣어도 됨(run_id·rubric·aggregate는 무시).
    """

    reactions: list[PersonaReaction]
    ad_analysis: AdInterpretation | None = None
    simulation_id: str | None = None  # 있으면 영속화 FK로 사용(없으면 인메모리만)
    personas: list[Persona] | None = None  # 인구통계(있으면 타깃 적합 선발 — 타깃 밖 후보 배제)


@router.post("/analyze")
async def analyze_reactions(body: DebateRequest) -> dict:
    """조각 8·9만 — 반응 분석·KPI·토론 주제를 즉시 반환(결정론·LLM✗·동기, 토론 전 미리보기)."""
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    return _mock_service.analyze(body.reactions, body.ad_analysis)


@router.post("/start")
async def start_debate(body: DebateRequest, use_llm: bool = False, lay_count: int = 4) -> dict:
    """JSON 데이터(reactions[])로 토론 시작 — 비동기. use_llm=true면 실 LLM(비용 발생).

    lay_count: 일반인 수(2=피벗·비판자 / 4=+완주자·미온). 패널 = 전문가4 + 일반인lay_count.
    두 버전을 같은 데이터로 돌려 비교할 수 있게 분리.
    """
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    if lay_count not in (2, 4):
        raise HTTPException(status_code=422, detail="lay_count는 2 또는 4여야 합니다.")
    run_id = await _svc(use_llm).start(
        body.reactions,
        body.ad_analysis,
        simulation_id=body.simulation_id,
        lay_count=lay_count,
        personas=body.personas,
    )
    return {"run_id": run_id, "stream_url": f"/api/debate/{run_id}/stream", "lay_count": lay_count}


@router.get("/{run_id}/stream")
async def stream_debate(run_id: str) -> StreamingResponse:
    """SSE — 단계별 진행 이벤트(analysis→…→utterance→round_summary→judge_final→report→completed)."""
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
