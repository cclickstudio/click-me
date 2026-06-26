import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.orchestration.bootstrap import build_orchestration
from api.orchestration.context import TurnContext
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import RouteDecision, Router
from api.orchestration.turn import build_orchestrator_graph, run_turn
from core.config import settings
from core.db import get_db
from core.models import ManagementChatMessage
from core.schemas import ChatMessage, ChatRequest
from domain.management.assistant.composer import compose_card, format_sse, stream_card
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.management.assistant.history import record_feedback, record_turn

router = APIRouter()

# CLIO 시스템 프롬프트 — LangChain SystemMessage로 주입(provider 공통).
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

_CLIO_ENGINE_LABEL = {"gemini": "Gemini", "openai": "OpenAI", "anthropic": "Claude"}


def _clio_messages(messages: list[ChatMessage]) -> list:
    """ChatMessage 목록을 LangChain 메시지로 — system(CLIO) + user/assistant 매핑."""
    out: list = [SystemMessage(content=_CLIO_SYSTEM)]
    for m in messages:
        out.append(
            HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content)
        )
    return out


def _build_clio_llm(provider: str) -> BaseChatModel:
    """provider별 LangChain 챗모델 — LangSmith 자동 계측·토큰·비용 포착(raw SDK 추적 누락 제거)."""
    if provider == "openai":
        from langchain_openai import ChatOpenAI  # noqa: PLC0415

        return ChatOpenAI(model=settings.chat_openai_model, api_key=settings.openai_api_key)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # noqa: PLC0415

        return ChatAnthropic(
            model=settings.chat_anthropic_model,
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

    return ChatGoogleGenerativeAI(
        model=settings.chat_gemini_model, google_api_key=settings.gemini_api_key
    )


# ── 오케스트레이션: 점수 라우터 + 도메인 에이전트 레지스트리(합성은 bootstrap) ──
# 도메인 추가는 bootstrap.build_orchestration의 매처/에이전트 등록으로. 여기선 판정·획득만.
_orchestration = None


def _get_orchestration() -> tuple[Router, AgentRegistry]:
    global _orchestration
    if _orchestration is None:
        _orchestration = build_orchestration(settings)
    return _orchestration


def _should_plan(route: RouteDecision, registry: AgentRegistry) -> bool:
    # 도메인이 해석되고(score>0) 그 도메인이 등록돼 있으면 Plan 경로. 아니면 CLIO.
    return route.score > 0.0 and registry.get(route.domain) is not None


_orchestrator_graph = None


def _get_orchestrator_graph() -> Any:
    # 컴파일된 StateGraph는 한 번만 빌드해 재사용(Router·Registry와 동일 lazy 패턴).
    global _orchestrator_graph
    if _orchestrator_graph is None:
        _, registry = _get_orchestration()
        _orchestrator_graph = build_orchestrator_graph(registry)
    return _orchestrator_graph


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

    # 1) 어시스턴트 호출 + 카드 조립 — 실패하면 안전 문구 error + final(failed). raw exception 미노출.
    try:
        t0 = time.perf_counter()
        result = await assistant(AskRequest(question=question, ad_id=ad_id, thread_id=thread_id))
        latency_ms = int((time.perf_counter() - t0) * 1000)
        card = compose_card(result, turn_id=thread_id)
    except Exception as exc:  # noqa: BLE001 — 턴 실패. 상세는 로그로만.
        print(f"[chat] management turn failed: {exc!r}")
        yield format_sse(
            {"kind": "error", "scope": "turn", "message": "매니지먼트 조회 중 문제가 발생했어요."}
        )
        yield format_sse({"kind": "final", "turn_id": thread_id, "status": "failed"})
        return

    # 2) 관측 적재는 best-effort — 실패해도 답변 스트림은 그대로.
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
    async for chunk in stream_card(card):
        yield chunk


async def _clio_stream(messages: list[ChatMessage], provider: str) -> AsyncGenerator[str, None]:
    """CLIO 어드바이저 — provider별 LangChain 챗모델로 SSE 스트림(meta→token→done).

    raw SDK 직접 호출을 제거해 LangSmith 추적 누락을 메우고, Gemini 스레드/큐 우회도 없앤다.
    """
    label = _CLIO_ENGINE_LABEL.get(provider, "Gemini")
    yield f"data: {json.dumps({'meta': {'source': 'clio', 'label': 'CLIO', 'engine': label}}, ensure_ascii=False)}\n\n"
    try:
        llm = _build_clio_llm(provider)
        async for chunk in llm.astream(_clio_messages(messages)):
            token = chunk.content
            if token:
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
    except Exception as exc:  # noqa: BLE001 — 스트림 실패를 정상 종료로 위장하지 않는다
        print(f"[chat] clio stream error ({provider}): {exc!r}")
        yield f"data: {json.dumps({'error': 'CLIO 응답 중 문제가 발생했어요.'}, ensure_ascii=False)}\n\n"
    yield 'data: {"done": true}\n\n'


@router.post("/complete")
async def chat_complete(body: ChatRequest) -> StreamingResponse:
    last_message = body.messages[-1].content if body.messages else ""

    async def generate() -> AsyncGenerator[str, None]:
        # 오케스트레이션 — 도메인이 해석·등록되면 고정 Plan 경로(turn 그래프)로, 아니면 CLIO.
        # S2: 라이브 카드 렌더는 management 단일 경로만(회귀 0). gen/sim·멀티스텝 렌더링은 S3+.
        router, registry = _get_orchestration()
        route = router.route(last_message)
        if _should_plan(route, registry) and route.domain == "management":
            graph = _get_orchestrator_graph()

            async def _assistant(req: AskRequest) -> AskResult:
                # 블랙보드 컨텍스트로 변환 — management 어댑터가 ctx/step→AskRequest로 되번역.
                ctx = TurnContext(
                    user_input=req.question,
                    session_id=body.session_id,
                    ad_id=req.ad_id,
                )
                return await run_turn(graph, route, ctx=ctx)

            async for chunk in _management_card_stream(
                question=last_message,
                session_id=body.session_id,
                ad_id=body.context_ad_id,
                assistant=_assistant,
                record=_record_management_turn,
            ):
                yield chunk
            return

        # 그 외는 CLIO 어드바이저 — LangChain 챗모델 SSE(기본 gemini, CHAT_PROVIDER로 전환).
        async for chunk in _clio_stream(body.messages, settings.chat_provider):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
async def list_sessions() -> dict:
    return {"sessions": []}


def _content_to_card(content: str | None) -> dict | None:
    """저장된 content가 카드 JSON이면 dict로 복원, 아니면 None(텍스트 메시지)."""
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) and parsed.get("version") == 1 else None


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        (
            await db.execute(
                select(ManagementChatMessage)
                .where(ManagementChatMessage.thread_id == session_id)
                .order_by(ManagementChatMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    messages = []
    for r in rows:
        card = _content_to_card(r.content)
        messages.append({"role": r.role, "content": None if card else r.content, "card": card})
    return {"session_id": session_id, "messages": messages}


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
