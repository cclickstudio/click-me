# 페르소나 토론 파이프라인 라우터 — 7번 반응 산출(JSON) → 8·9 분석 / 8~11 토론(SSE)
#
# 입력은 JSON body(reactions[])로 통일. 분석(analyze)은 동기 즉시 반환, 토론(start)은 SSE 비동기.
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core.config import settings
from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.contracts.debate_schemas import DebateTopic
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    ObjectiveFit,
    Persona,
    PersonaReaction,
    RubricScore,
)
from domain.simulation.tools.debate.pdf_report import render_report_pdf
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
    # 광고 제목·설명 — 토론 주제(topic)에 동봉돼 토론자 grounding·analyze 응답으로 흐름.
    ad_title: str | None = None
    ad_description: str | None = None
    # 추가 토론: 사용자가 /topics 후보 중 고른 논제(없으면 분석 headline 고정 = 최초 토론).
    topic: DebateTopic | None = None
    # §4 루브릭 점수(시뮬 결과에 포함) — 있으면 리포트 크리에이티브 진단에 그대로 실음.
    rubric_scores: list[RubricScore] | None = None
    # 캠페인 목표 적합도(시뮬 결과에 포함) — ReportView 메인 판정. DB 영속 없어 직접 동봉.
    objective_fit: ObjectiveFit | None = None


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
    return _service.analyze(body.reactions, body.ad_analysis, body.ad_title, body.ad_description)


@router.post("/topics")
async def debate_topics(body: DebateRequest) -> dict:
    """추가 토론용 논제 후보 5개(결정론·LLM✗). 사용자가 이 중 하나를 골라 /start의 topic으로 전달.

    반환: {"topics": [DebateTopic, ...]} — ranking·confidence 순 정렬. (본문 로직은 코어 트랙 T1)
    """
    if not body.reactions:
        raise HTTPException(status_code=422, detail="reactions가 비어 있습니다.")
    return _service.build_candidates(
        body.reactions, body.ad_analysis, body.ad_title, body.ad_description
    )


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
        objective_fit=body.objective_fit,  # 캠페인 목표 적합도(ReportView 메인 판정)
        ad_title=body.ad_title,  # 광고 제목 — 최초 토론 topic에 동봉(토론자 grounding)
        ad_description=body.ad_description,  # 광고 설명 — 동상
    )
    return {"run_id": run_id, "stream_url": f"/api/debate/{run_id}/stream", "lay_count": lay_count}


@router.get("/by-simulation/{simulation_id}")
async def list_sessions(simulation_id: str) -> dict:
    """simulation_id로 저장된(DB) 토론 목록 — 메타만(발언 제외). 영속화 미주입이면 빈 목록.

    프로젝트 패널·세션 탭 복원용. {"debates": [{debate_id·topic·status·headline·…}, ...]}.
    """
    return {"debates": await _service.list_saved(simulation_id)}


@router.get("/by-simulation/{simulation_id}/report")
async def get_saved_report(simulation_id: str) -> dict:
    """simulation_id로 저장된 통합 리포트(report_view) — 새로고침·콜드 진입 시 최종 리포트 복원.

    DB에 영속된 simulation_reports 1행의 report_view를 반환. 없으면 404(DB 미연동·미저장 포함).
    """
    report_view = await _service.get_saved_report(simulation_id)
    if report_view is None:
        raise HTTPException(status_code=404, detail="저장된 리포트 없음(DB 미연동·미저장 가능)")
    return report_view


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


@router.get("/{run_id}/report.pdf")
async def download_report_pdf(run_id: str) -> Response:
    """완료된 리포트를 PDF로 생성해 다운로드(서버 Chromium 렌더).

    콜드·새로고침 진입에선 인메모리 run_id가 죽어 있으므로, 못 찾으면 simulation_id로
    간주해 저장 리포트를 재조립한다(화면 최종 결과와 동일 소스).
    """
    result = _service.get_result(run_id)
    if result is None:
        report_view = await _service.get_saved_report(run_id)
        if report_view is None:
            raise HTTPException(status_code=404, detail="결과 없음 또는 토론 미완료")
        result = {"report_view": report_view}
    pdf = await asyncio.to_thread(render_report_pdf, result)  # sync Playwright를 스레드로 분리
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{run_id}.pdf"'},
    )


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
