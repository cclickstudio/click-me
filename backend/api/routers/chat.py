# 챗 라우터 — 오케스트레이터 구동 및 세션/메시지 조회 엔드포인트.
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import settings
from core.schemas import ChatRequest
from domain.chat.contracts.agent_io import ChatTurnRequest
from domain.chat.service.orchestrator import ChatOrchestratorService
from domain.chat.wiring import build_chat_repo, build_orchestrator
from domain.management.assistant.history import record_feedback

router = APIRouter()


def _opt_uuid(value: str | None, field: str) -> uuid.UUID | None:
    """옵션 UUID 파싱 — 빈값이면 None, 잘못된 형식이면 400."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"{field}가 유효한 UUID 형식이 아닙니다."
        ) from exc


def _build_turn_request(body: ChatRequest) -> ChatTurnRequest:
    """ChatRequest(전송) → ChatTurnRequest(도메인). 마지막 메시지=user_text, 그 앞=history.

    멀티테넌트 id(project/user/organization)는 인증 도입 전까지 본문에서 수용한다.
    """
    try:
        session_uuid = uuid.UUID(body.session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="session_id가 유효한 UUID 형식이 아닙니다."
        ) from exc

    last = body.messages[-1].content if body.messages else ""
    history = [{"role": m.role, "content": m.content} for m in body.messages[:-1]]

    return ChatTurnRequest(
        session_id=session_uuid,
        user_text=last,
        history=history,
        project_id=_opt_uuid(body.project_id, "project_id"),
        user_id=_opt_uuid(body.user_id, "user_id"),
        organization_id=_opt_uuid(body.organization_id, "organization_id"),
        context_ad_id=body.context_ad_id,
        context_campaign_id=body.context_campaign_id,
        context_simulation_id=body.context_simulation_id,
        context_ad_image_url=body.context_ad_image_url,
        context_ad_image_key=body.context_ad_image_key,
    )


# 챗 오케스트레이터 싱글톤 — 체크포인터 풀을 1회 조립·공유하고 lifespan 종료 시 정리한다.
_orchestrator: ChatOrchestratorService | None = None


async def get_orchestrator() -> ChatOrchestratorService:
    """오케스트레이터 싱글톤 — 최초 호출 시 1회 조립(체크포인터 포함), 이후 재사용."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = await build_orchestrator(settings)
    return _orchestrator


async def close_orchestrator() -> None:
    """lifespan 종료 훅 — 오케스트레이터 체크포인터 풀을 정리한다(미생성이면 no-op)."""
    global _orchestrator
    if _orchestrator is not None:
        await _orchestrator.aclose()
        _orchestrator = None


class ResumeRequest(BaseModel):
    approved: bool
    approver_id: str | None = None


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10MB


@router.post("/complete")
async def chat_complete(body: ChatRequest) -> StreamingResponse:
    """마지막 사용자 메시지를 오케스트레이터에 전달하고 SSE 스트림을 반환한다."""
    req = _build_turn_request(body)
    svc = await get_orchestrator()
    return StreamingResponse(svc.stream(req), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/upload-image")
async def chat_upload_image(file: UploadFile = File(...)) -> dict:
    """채팅 첨부 이미지를 S3에 영속화하고 시뮬 트리거용 참조를 반환한다.

    ad_id는 이 이미지로 돌릴 광고 식별자로 새로 발급. 프론트는 이 응답을 다음 /complete 요청의
    context_ad_id·context_ad_image_url·context_ad_image_key로 실어 보내면 "시뮬 돌려줘"에 트리거된다.
    """
    from domain.simulation.adapters.ad_image_store import persist_ad_image

    data = await file.read()
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(최대 10MB)")
    url, key = await persist_ad_image(data, file.filename, file.content_type)
    return {"ad_id": str(uuid.uuid4()), "ad_image_url": url, "ad_image_key": key}


@router.post("/{thread_id}/resume")
async def chat_resume(thread_id: str, body: ResumeRequest) -> StreamingResponse:
    """HITL 승인/거부 후 인터럽트된 그래프를 재개하고 SSE 스트림을 반환한다."""
    svc = await get_orchestrator()
    decision = {"approved": body.approved, "approver_id": body.approver_id or "user"}
    return StreamingResponse(
        svc.resume(thread_id, decision), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.get("/sessions")
async def list_sessions() -> dict:
    """저장된 채팅 세션 목록을 반환한다."""
    repo = build_chat_repo(settings)
    sessions = await repo.list_sessions(user_id=None, limit=50)
    return {"sessions": [s.model_dump(mode="json") for s in sessions]}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict:
    """특정 세션의 메시지 목록을 반환한다."""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="session_id가 유효한 UUID 형식이 아닙니다."
        ) from exc

    repo = build_chat_repo(settings)
    msgs = await repo.get_messages(session_uuid, limit=200)
    return {"session_id": session_id, "messages": [m.model_dump(mode="json") for m in msgs]}


class FeedbackRequest(BaseModel):
    thread_id: str | None = None  # 채팅 세션 키(mgmt-{session_id})
    message_id: str | None = None
    question: str | None = None
    answer: str | None = None
    rating: int | None = None  # 1 좋아요 / -1 싫어요
    failure_type: str | None = None  # wrong_tool|stale_doc|hallucinated_number|missing_citation 등
    corrected_answer: str | None = None


@router.post("/feedback")
async def chat_feedback(body: FeedbackRequest) -> dict:
    """어시스턴트 답변 피드백 적재 — RAG 품질 개선 루프(management_kb_feedback). best-effort."""
    await record_feedback(
        thread_id=body.thread_id,
        message_id=body.message_id,
        question=body.question,
        answer=body.answer,
        rating=body.rating,
        failure_type=body.failure_type,
        corrected_answer=body.corrected_answer,
    )
    return {"ok": True}
