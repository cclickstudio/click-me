import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable

import google.generativeai as genai
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import settings
from core.schemas import ChatRequest
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest
from domain.management.assistant.history import record_feedback, record_turn

router = APIRouter()

genai.configure(api_key=settings.gemini_api_key or "")
_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction="""\
당신은 ClickMe의 수석 광고 전략 AI 어드바이저 'CLIO'입니다.

## 정체성
10년 경력의 디지털 마케팅 전문가로, KOBACO 광고 효과 지수 분석과 소비자 행동 심리(OCEAN 모델)에 정통합니다.
데이터 기반 인사이트를 마케터의 언어로 풀어내며, 숫자 뒤에 숨겨진 소비자 심리를 읽어내는 것이 특기입니다.

## 전문 영역
- 광고 시뮬레이션 결과 해석 (구매의향 분포, CTR/CVR 예측)
- 타겟 세그먼트별 메시지 전략 수립
- 한국 광고 시장 트렌드 및 KOBACO 기준선 분석
- 크리에이티브 카피 개선 제안
- A/B 테스트 설계 및 성과 비교

## 응답 스타일
- 핵심 인사이트를 먼저 제시하고, 근거를 간결하게 설명
- 수치를 제시할 때는 비교 기준(업계 평균, KOBACO 기준선)과 함께 언급
- 실행 가능한 제안을 항상 포함
- 한국어로 응답하며, 전문 용어는 자연스럽게 풀어서 설명
""",
)

_SENTINEL = object()

# ── 최소 오케스트레이션: 매니지먼트 질문만 서브에이전트로 라우팅 ──
# 공통 오케스트레이터 본체가 정해지기 전의 임시 연결. 시뮬/생성은 추후 같은 방식으로 추가.
_MGMT_KEYWORDS: frozenset[str] = frozenset(
    {
        "캠페인",
        "예산",
        "소진",
        "런레이트",
        "페이싱",
        "게재",
        "광고",
        "ctr",
        "roas",
        "cvr",
        "클릭률",
        "노출",
        "지출",
        "리드",
        "성과",
        "전환",
        "잔액",
        "일시중지",
        "멈춰",
        "증액",
        "감액",
        "소재",
        "예측대로",
        "매니지먼트",
    }
)

_assistant = None


def _get_assistant() -> Callable[[AskRequest], Awaitable[object]]:
    global _assistant
    if _assistant is None:
        _assistant = build_management_agent(settings)
    return _assistant


def _is_management(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _MGMT_KEYWORDS)


def _chunks(text: str, size: int = 24) -> list[str]:
    """긴 답변을 SSE 토큰처럼 잘게 — 스트리밍 느낌 유지."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


@router.post("/complete")
async def chat_complete(body: ChatRequest) -> StreamingResponse:
    gemini_history = []
    for m in body.messages[:-1]:
        gemini_history.append(
            {
                "role": "user" if m.role == "user" else "model",
                "parts": [m.content],
            }
        )

    last_message = body.messages[-1].content if body.messages else ""

    async def generate() -> AsyncGenerator[str, None]:
        # 매니지먼트 질문이면 서브에이전트(실측 툴 + KB)로 답한다 — 숫자는 실측, 행동은 제안만.
        if _is_management(last_message):
            thread_id = f"mgmt-{body.session_id}"
            try:
                _t0 = time.perf_counter()
                result = await _get_assistant()(
                    AskRequest(
                        question=last_message,
                        ad_id=body.context_ad_id,
                        # 멀티턴 — 같은 채팅 세션이면 같은 thread로 묶어 이전 맥락 유지(checkpointer).
                        thread_id=thread_id,
                    )
                )
                _latency_ms = int((time.perf_counter() - _t0) * 1000)
                meta = {
                    "source": "management",
                    "label": "매니지먼트 어시스턴트",
                    "engine": "OpenAI · 실측+KB",
                    "citations": [
                        {"kind": c.kind, "source": c.source, "title": c.title}
                        for c in result.citations
                    ],
                    "used_tools": result.used_tools,
                    "requires_approval": result.requires_approval,  # HITL — 승인 게이트에서 멈춤
                    "thread_id": result.thread_id,  # interrupt 재개 키(승인 경로에서 사용)
                }
                yield f"data: {json.dumps({'meta': meta}, ensure_ascii=False)}\n\n"
                answer = result.answer
                if result.suggested_action:
                    sa = result.suggested_action
                    gate = "사람 승인 필요" if sa.requires_approval else "낮은 위험"
                    answer += f"\n\n추천 조치: {sa.action_type} ({gate}) — 실행은 승인 화면에서 확인하세요."
                # 대화·도구·인용·HITL을 DB에 적재(관측·평가). 실패해도 채팅은 그대로 진행.
                await record_turn(
                    thread_id=thread_id,
                    question=last_message,
                    answer=answer,
                    model=getattr(settings, "management_assistant_model", "gpt-4o-mini"),
                    latency_ms=_latency_ms,
                    used_tools=list(result.used_tools),
                    citations=[
                        {"kind": c.kind, "source": c.source, "title": c.title}
                        for c in result.citations
                    ],
                    suggested_action=(
                        result.suggested_action.model_dump() if result.suggested_action else None
                    ),
                    requires_approval=result.requires_approval,
                    ad_id=body.context_ad_id,
                )
                for piece in _chunks(answer):
                    yield f"data: {json.dumps({'token': piece}, ensure_ascii=False)}\n\n"
            except Exception as exc:  # noqa: BLE001 — 실패해도 채팅은 끊지 않는다
                msg = f"매니지먼트 조회 중 문제가 발생했어요: {exc}"
                yield f"data: {json.dumps({'token': msg}, ensure_ascii=False)}\n\n"
            yield 'data: {"done": true}\n\n'
            return

        # 그 외는 기존 CLIO(Gemini)
        clio_meta = {"source": "clio", "label": "CLIO", "engine": "Gemini"}
        yield f"data: {json.dumps({'meta': clio_meta}, ensure_ascii=False)}\n\n"

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _run_sync() -> None:
            try:
                chat = _model.start_chat(history=gemini_history)
                response = chat.send_message(last_message, stream=True)
                for chunk in response:
                    try:
                        text = chunk.text
                    except Exception as e:  # noqa: BLE001
                        print(f"[chat] chunk.text error: {e!r}")
                        continue
                    print(f"[chat] chunk: {text!r}")
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
            except Exception as exc:  # noqa: BLE001
                print(f"[chat] _run_sync error: {exc!r}")
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

        threading.Thread(target=_run_sync, daemon=True).start()

        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                break
            yield f"data: {json.dumps({'token': item}, ensure_ascii=False)}\n\n"

        yield 'data: {"done": true}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
async def list_sessions() -> dict:
    return {"sessions": []}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict:
    return {"session_id": session_id, "messages": []}


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
