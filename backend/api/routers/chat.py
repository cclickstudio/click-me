import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable

import google.generativeai as genai
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from api.orchestration.bootstrap import build_orchestration
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import Router
from core.config import settings
from core.schemas import ChatMessage, ChatRequest
from domain.management.assistant.composer import compose_turn, format_sse, stream_turn
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.management.assistant.history import record_feedback, record_turn

router = APIRouter()

# CLIO 시스템 프롬프트 — Gemini는 system_instruction, OpenAI는 system 메시지로 공유.
_CLIO_SYSTEM = """\
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
"""

genai.configure(api_key=settings.gemini_api_key or "")
_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=_CLIO_SYSTEM,
)
_openai = AsyncOpenAI(api_key=settings.openai_api_key)

_SENTINEL = object()

# ── 오케스트레이션: 점수 라우터 + 도메인 에이전트 레지스트리(합성은 bootstrap) ──
# 도메인 추가는 bootstrap.build_orchestration의 매처/에이전트 등록으로. 여기선 판정·획득만.
_orchestration = None


def _get_orchestration() -> tuple[Router, AgentRegistry]:
    global _orchestration
    if _orchestration is None:
        _orchestration = build_orchestration(settings)
    return _orchestration


def _resolve_domain(text: str) -> str:
    router, _ = _get_orchestration()
    return router.route(text).domain


async def _record_management_turn(
    *, thread_id: str, result: AskResult, question: str, ad_id: str | None, latency_ms: int
) -> None:
    # record_turn 어댑터 — AskResult를 record_turn 인자로 매핑(기본 record 구현).
    await record_turn(
        thread_id=thread_id,
        question=question,
        answer=result.answer,
        model=getattr(settings, "management_assistant_model", "gpt-4o-mini"),
        latency_ms=latency_ms,
        used_tools=list(result.used_tools),
        citations=[
            {"kind": c.kind, "source": c.source, "title": c.title} for c in result.citations
        ],
        suggested_action=(
            result.suggested_action.model_dump() if result.suggested_action else None
        ),
        requires_approval=result.requires_approval,
        ad_id=ad_id,
    )


async def _management_card_stream(
    *,
    question: str,
    session_id: str,
    ad_id: str | None,
    assistant: Callable[[AskRequest], Awaitable[AskResult]],
    record: Callable[..., Awaitable[None]],
) -> AsyncGenerator[str, None]:
    # 매니지먼트 한 턴을 카드 SSE로. assistant/record 주입 → 앱·DB 없이 테스트 가능.
    thread_id = f"mgmt-{session_id}"

    # 1) 어시스턴트 호출 + 봉투 조립 — 여기서 실패하면 진짜 턴 실패(아직 아무것도 yield 안 함).
    try:
        t0 = time.perf_counter()
        result = await assistant(AskRequest(question=question, ad_id=ad_id, thread_id=thread_id))
        latency_ms = int((time.perf_counter() - t0) * 1000)
        env = compose_turn(result, turn_id=thread_id)
    except Exception as exc:  # noqa: BLE001 — 어시스턴트/조립 실패 = 턴 실패
        yield format_sse(
            {
                "event": "error",
                "scope": "turn",
                "code": "assistant_error",
                "message": f"매니지먼트 조회 중 문제가 발생했어요: {exc}",
            }
        )
        yield format_sse({"event": "final", "turn_id": thread_id, "status": "failed"})
        return

    # 2) 관측 적재는 best-effort — 실패해도 답변 스트림은 그대로(원래 chat.py 동작 보존).
    try:
        await record(
            thread_id=thread_id,
            result=result,
            question=question,
            ad_id=ad_id,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 — 적재 실패는 채팅을 끊지 않는다
        print(f"[chat] record_turn failed (best-effort, ignored): {exc!r}")

    # 3) 정상 답변 스트리밍.
    async for chunk in stream_turn(env):
        yield chunk


async def _clio_openai_stream(messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
    # CLIO를 OpenAI로 — 네이티브 async 스트림(Gemini의 스레드/큐 우회 불필요). meta/token/done 동일.
    yield f"data: {json.dumps({'meta': {'source': 'clio', 'label': 'CLIO', 'engine': 'OpenAI'}}, ensure_ascii=False)}\n\n"
    oai_messages = [{"role": "system", "content": _CLIO_SYSTEM}]
    for m in messages:
        oai_messages.append(
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        )
    try:
        stream = await _openai.chat.completions.create(
            model=settings.chat_openai_model, messages=oai_messages, stream=True
        )
        async for chunk in stream:
            if not chunk.choices:  # usage-only 청크 등 — choices가 비는 경우 방어
                continue
            token = chunk.choices[0].delta.content
            if token:
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
    except Exception as exc:  # noqa: BLE001 — 스트림 실패를 정상 종료로 위장하지 않는다
        print(f"[chat] openai stream error: {exc!r}")
        yield f"data: {json.dumps({'error': 'OpenAI 응답 중 문제가 발생했어요.'}, ensure_ascii=False)}\n\n"
    yield 'data: {"done": true}\n\n'


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
        # MVP 임시 분기 — sim/gen 도메인 에이전트 등록 전까지 management만 카드 스트림에 연결한다.
        # (도메인 추가 시 이 분기를 레지스트리 디스패치로 일반화)
        _, registry = _get_orchestration()
        domain = _resolve_domain(last_message)
        if domain == "management":
            agent = registry.get(domain)
            if agent is None:  # 정상 bootstrap이면 반드시 존재 — 없으면 설정 오류, 조용한 폴백 금지
                raise RuntimeError(
                    "management로 라우팅됐으나 에이전트 미등록 — bootstrap 설정 오류"
                )
            async for chunk in _management_card_stream(
                question=last_message,
                session_id=body.session_id,
                ad_id=body.context_ad_id,
                assistant=agent.ask,
                record=_record_management_turn,
            ):
                yield chunk
            return

        # 그 외는 CLIO 어드바이저 — provider 토글(기본 gemini, CHAT_PROVIDER=openai면 OpenAI).
        if settings.chat_provider == "openai":
            async for chunk in _clio_openai_stream(body.messages):
                yield chunk
            return

        # 기본 CLIO(Gemini)
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
