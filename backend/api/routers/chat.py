"""Chat router — Claude Sonnet SSE 스트리밍."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    project_id: str | None = None


@router.post("/")
async def chat(body: ChatRequest) -> dict:
    # TODO: Chat Agent (Claude Sonnet) SSE 스트리밍 연결
    raise NotImplementedError


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    # TODO: 채팅 세션 히스토리 조회
    raise NotImplementedError
