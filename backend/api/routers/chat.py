import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from anthropic import AsyncAnthropic

from core.schemas import ChatRequest

router = APIRouter()
_anthropic = AsyncAnthropic()

SYSTEM_PROMPT = """\
당신은 ClickMe의 광고 분석 AI 어시스턴트입니다.
마케터가 광고 성과를 이해하고 개선하는 데 도움을 드립니다.
시뮬레이션 결과를 해석하고, 광고 전략을 조언하며, 광고 관련 질문에 답변합니다."""


@router.post("/complete")
async def chat_complete(body: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    async def generate():
        async with _anthropic.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'token': text}, ensure_ascii=False)}\n\n"
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/sessions")
async def list_sessions():
    return {"sessions": []}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    return {"session_id": session_id, "messages": []}
