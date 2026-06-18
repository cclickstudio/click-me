# 페르소나 토론 파이프라인 라우터 — 7번 반응 산출(JSON) → 8·9 분석 / 8~11 토론(SSE)
#
# 입력은 JSON body(reactions[])로 통일. 분석(analyze)은 동기 즉시 반환, 토론(start)은 SSE 비동기.
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import settings
from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.contracts.debate_schemas import DebateTopic
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Persona,
    PersonaReaction,
    RubricScore,
)
from domain.simulation.wiring import build_debate_service

router = APIRouter()

# 토론은 항상 실 LLM(Haiku/GPT 토론자 + Sonnet Judge + 선발 LLM 게이트). mock 토론 경로 제거.
# settings 주입 → settings.database_url 있으면 토론 영속화 활성(persona_debates·participants·
# utterances 3테이블 저장). simulation_id가 함께 와야 FK(NOT NULL) 충족돼 실제 저장된다.
_store = InMemorySimulationStore()
_service = build_debate_service(settings=settings, use_mock=False, store=_store)


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class DebateRequest(BaseModel):
    """토론/분석 입력 — 7번(반응 출력) 산출물. reactions 필수, 나머지 선택.

    더미·시뮬레이션 결과 JSON 전체를 그대로 붙여넣어도 됨(run_id·aggregate는 무시).
    """

    reactions: list[PersonaReaction]
    ad_analysis: AdInterpretation | None = None
    simulation_id: str | None = None  # 있으면 영속화 FK로 사용(없으면 인메모리만)
    personas: list[Persona] | None = None  # 인구통계(있으면 타깃 적합 선발 — 타깃 밖 후보 배제)
    # 추가 토론: 사용자가 /topics 후보 중 고른 논제(없으면 분석 headline 고정 = 최초 토론).
    topic: DebateTopic | None = None
    # §4 루브릭 점수(시뮬 결과에 포함) — 있으면 리포트 크리에이티브 진단에 그대로 실음.
    rubric_scores: list[RubricScore] | None = None


class QuestionRequest(BaseModel):
    """토론 종료 후 Q&A 입력 — 사용자 질문 + 답변 grounding용 reactions(토론 때와 동일)."""

    question: str
    reactions: list[PersonaReaction]
    ad_analysis: AdInterpretation | None = None


@router.post("/analyze")
async def analyze_reactions(body: DebateRequest) -> dict:
    """조각 8·9만 — 반응 분석·KPI·토론 주제를 즉시 반환(결정론·LLM✗·동기, 토론 전 미리보기)."""
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    return _service.analyze(body.reactions, body.ad_analysis)


@router.post("/topics")
async def debate_topics(body: DebateRequest) -> dict:
    """추가 토론용 논제 후보 5개(결정론·LLM✗). 사용자가 이 중 하나를 골라 /start의 topic으로 전달.

    반환: {"topics": [DebateTopic, ...]} — ranking·confidence 순 정렬. (본문 로직은 코어 트랙 T1)
    """
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    return _service.build_candidates(body.reactions, body.ad_analysis)


@router.post("/start")
async def start_debate(body: DebateRequest, lay_count: int = 3) -> dict:
    """JSON 데이터(reactions[])로 토론 시작 — 비동기. 토론은 항상 실 LLM(비용 발생).

    lay_count: 일반인 수(2=피벗·비판자 / 3=+완주자 / 4=+완주자·미온). 패널 = 전문가4 + 일반인.
    """
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    if lay_count not in (2, 3, 4):
        raise HTTPException(status_code=422, detail="lay_count는 2, 3, 4 중 하나여야 합니다.")
    run_id = await _service.start(
        body.reactions,
        body.ad_analysis,
        simulation_id=body.simulation_id,
        lay_count=lay_count,
        personas=body.personas,
        topic=body.topic,  # 선택 논제(없으면 최초 토론 = 분석 headline 고정)
        rubric=body.rubric_scores,  # §4 루브릭(있으면 리포트에 실음)
    )
    return {"run_id": run_id, "stream_url": f"/api/debate/{run_id}/stream", "lay_count": lay_count}


@router.get("/by-simulation/{simulation_id}")
async def list_sessions(simulation_id: str) -> dict:
    """simulation_id로 저장된(DB) 토론 목록 — 메타만(발언 제외). 영속화 미주입이면 빈 목록.

    프로젝트 패널·세션 탭 복원용. {"debates": [{debate_id·topic·status·headline·…}, ...]}.
    """
    return {"debates": await _service.list_saved(simulation_id)}


@router.get("/{debate_id}/detail")
async def get_session(debate_id: str) -> dict:
    """저장된 토론 1건 상세(participants + 라운드순 발언 + judge_log + final) — 복원·표시용."""
    detail = await _service.get_saved(debate_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="저장된 토론 없음(DB 미연동 가능)")
    return detail


@router.get("/{run_id}/stream")
async def stream_debate(run_id: str) -> StreamingResponse:
    """SSE — 단계별 진행 이벤트(analysis→…→utterance→round_summary→judge_final→report→completed)."""
    return StreamingResponse(
        _service.stream_events(run_id),  # store 공유라 서비스 무관(run_id 기반)
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/{run_id}/result")
async def debate_result(run_id: str) -> dict:
    """완료된 토론 결과(analysis·aggregate·topic·panel·debate·report)."""
    result = _service.get_result(run_id)  # store 공유라 서비스 무관
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음 또는 토론 미완료")
    return result


@router.post("/{run_id}/question")
async def ask_question(run_id: str, body: QuestionRequest) -> StreamingResponse:
    """토론 종료 후 Q&A — 패널 참가자가 순차로 답변(SSE). run_id의 패널·주제를 재사용.

    이벤트: qa_utterance(참가자별 답변) → qa_completed. (본문 로직은 Q&A 트랙 T2)
    """
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question이 비어 있습니다.")
    return StreamingResponse(
        _service.ask_question(run_id, body.question, body.reactions, body.ad_analysis),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
