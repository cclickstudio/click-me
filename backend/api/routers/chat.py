import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import AsyncSessionLocal, get_db
from core.schemas import ChatRequest
from domain.chat import history
from domain.chat.orchestrator import ChatTurn, build_chat_orchestrator
from tools.storage.s3 import download_bytes, upload_bytes

# 채팅 첨부 이미지 — 허용 타입과 S3 프리픽스(프록시 게이트).
_ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
_CHAT_IMAGE_PREFIX = "chat-images/"

router = APIRouter()
# 팀 구조 엔드포인트 — POST /api/assistant/chat (기존 /api/chat/complete와 동일 로직 공유)
assistant_router = APIRouter()

# 채팅 답변 엔진은 OpenAI 오케스트레이터로 일원화(Gemini 경로 제거).
# 풀모드면 classify → route → 도메인 서브에이전트/advise, 키 없으면 키워드 폴백(매니지).
_orchestrator = None


def _get_orchestrator() -> Callable[[ChatTurn], Awaitable[object]]:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_chat_orchestrator(settings)
    return _orchestrator


def _chunks(text: str, size: int = 24) -> list[str]:
    """긴 답변을 SSE 토큰처럼 잘게 — 스트리밍 느낌 유지."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


async def _persist(
    session_id: str,
    user_content: str,
    assistant_content: str,
    meta: dict | None,
    image_url: str | None = None,
    result_ref: dict | None = None,
) -> None:
    """한 턴을 DB에 적재(best-effort) — 세션 없거나 실패해도 채팅은 진행."""
    user_meta: dict = {}
    if image_url:
        user_meta["image_url"] = image_url
    if result_ref:
        user_meta["result"] = result_ref
    try:
        async with AsyncSessionLocal() as db:
            await history.append_turn(
                db, session_id, user_content, assistant_content, meta, user_meta=user_meta
            )
    except Exception as exc:  # noqa: BLE001 — 영속화 실패가 응답을 막지 않게
        print(f"[chat] persist error: {exc!r}")


@router.post("/complete")
@assistant_router.post("/chat")
async def chat_complete(body: ChatRequest) -> StreamingResponse:
    last_message = body.messages[-1].content if body.messages else ""

    async def generate() -> AsyncGenerator[str, None]:
        # 오케스트레이터(OpenAI) 단일 경로 — classify → route → 도메인 서브에이전트/advise.
        try:
            orch = await _get_orchestrator()(
                ChatTurn(
                    question=last_message,
                    history=[(m.role, m.content) for m in body.messages[:-1]],
                    ad_id=body.context_ad_id,
                    session_id=body.session_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 — 실패해도 스트림은 안내로 마무리
            print(f"[chat] orchestrator error: {exc!r}")
            orch = None

        if orch is not None:
            answer, meta = orch.answer, orch.meta
        else:
            # OpenAI 키 미설정 등으로 답을 못 받은 경우 — Gemini 폴백 없이 안내(엔진 일원화).
            answer = "지금은 답변을 생성할 수 없어요. 잠시 후 다시 시도해주세요."
            meta = {"source": "orchestrator", "label": "CLIO", "engine": "OpenAI"}

        yield f"data: {json.dumps({'meta': meta}, ensure_ascii=False)}\n\n"
        for piece in _chunks(answer):
            yield f"data: {json.dumps({'token': piece}, ensure_ascii=False)}\n\n"
        await _persist(
            body.session_id, last_message, answer, meta, body.image_url, body.result_ref
        )
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class SessionCreate(BaseModel):
    project_id: str | None = None
    title: str | None = None


@router.post("/sessions")
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)) -> dict:
    """새 채팅 세션 생성 — 프로젝트에 귀속."""
    s = await history.create_session(db, body.project_id, body.title)
    return {
        "id": str(s.id),
        "title": s.title,
        "project_id": str(s.project_id) if s.project_id else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/sessions")
async def list_sessions(project_id: str | None = None, db: AsyncSession = Depends(get_db)) -> dict:
    """프로젝트의 채팅 세션 목록 — 최근 갱신 순."""
    return {"sessions": await history.list_sessions(db, project_id)}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """세션의 메시지 내역."""
    return {"session_id": session_id, "messages": await history.get_messages(db, session_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """세션 삭제(메시지 CASCADE)."""
    return {"deleted": await history.delete_session(db, session_id)}


@router.post("/image")
async def upload_chat_image(file: UploadFile = File(...)) -> dict:
    """채팅 첨부 이미지 → S3 업로드 → 프록시 URL 반환(내역 영속화용)."""
    ct = (file.content_type or "").split(";")[0].strip()
    if ct not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="PNG·JPEG·WebP·GIF 이미지만 업로드 가능합니다.")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="이미지는 8MB 이하여야 합니다.")
    ext = _ALLOWED_IMAGE_TYPES[ct]
    key = f"{_CHAT_IMAGE_PREFIX}{uuid.uuid4().hex}.{ext}"
    await upload_bytes(data, key, content_type=ct)
    return {"key": key, "url": f"/api/chat/image?key={quote(key, safe='')}"}


@router.get("/image")
async def proxy_chat_image(key: str) -> Response:
    """채팅 첨부 이미지 S3 프록시 — chat-images/ 프리픽스만 허용(오픈 프록시 방지)."""
    if ".." in key or not key.startswith(_CHAT_IMAGE_PREFIX):
        raise HTTPException(status_code=403, detail="허용되지 않은 이미지 경로입니다.")
    try:
        data = await download_bytes(key)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.") from None
    if key.endswith((".jpg", ".jpeg")):
        media = "image/jpeg"
    elif key.endswith(".webp"):
        media = "image/webp"
    elif key.endswith(".gif"):
        media = "image/gif"
    else:
        media = "image/png"
    return Response(content=data, media_type=media)
