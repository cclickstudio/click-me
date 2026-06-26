import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant.orchestrator import Orchestrator
from api.assistant.wiring import build_assistant
from core.assistant_contracts import Action, ProjectRef, SubagentRequest, SubagentResult
from core.auth import optional_user
from core.config import settings
from core.db import get_db
from core.models import OrganizationMember, User
from core.schemas import ChatRequest
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest
from domain.management.assistant.history import record_feedback, record_turn

router = APIRouter()

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

## 응답 길이 규칙 (엄수)
- 답변은 **최대 3문장** 이내로 작성한다.
- 매 턴마다 자기소개·역할 설명·배경 설명을 반복하지 않는다.
- 정보를 수집해야 할 때는 질문을 **한 번에 하나씩**만 한다. 여러 항목을 번호 목록으로 한꺼번에 묻지 않는다.
- 부연 설명이나 감탄사("아주 중요한 단계죠!" 등) 없이 바로 본론으로 들어간다.
"""

_clio_client: AsyncOpenAI | None = None


def _get_clio_client() -> AsyncOpenAI:
    global _clio_client
    if _clio_client is None:
        _clio_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _clio_client

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


_orchestrator = None


def _get_orchestrator() -> Orchestrator:
    """교통정리(오케스트레이터) 1회 빌드·캐시 — 생성·관리 서브에이전트 조립."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_assistant(settings)
    return _orchestrator


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _subagent_sse_events(result: SubagentResult) -> Iterator[str]:
    """서브에이전트 결과(ANSWER/ASK/TRIGGER)를 SSE 이벤트로 변환. done은 호출자가 붙인다.

    - meta가 있으면 먼저 보낸다(출처·엔진·인용 표시).
    - TRIGGER면 started_event(stream_url)를 방출 — 프론트가 그 잡 진행을 구독한다.
    - message는 토큰처럼 잘게 스트리밍(되묻기 질문·확인·즉답 공통).
    """
    if result.meta:
        yield _sse({"meta": result.meta})
    if result.action == Action.TRIGGER and result.started_event is not None:
        yield _sse({"started": result.started_event.model_dump()})
    for piece in _chunks(result.message):
        yield _sse({"token": piece})


async def _get_user_projects(user: User, db: AsyncSession) -> list[ProjectRef]:
    """로그인 유저가 접근 가능한 프로젝트 목록 — 슬롯필링 되묻기용."""
    from sqlalchemy import text  # noqa: PLC0415

    base = "status != 'DELETED' AND deleted_at IS NULL"
    if user.role.upper() == "ADMIN":
        rows = await db.execute(
            text(f"SELECT id, name FROM projects WHERE {base} ORDER BY created_at DESC LIMIT 20")
        )
    else:
        member = await db.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
        if not member:
            return []
        org_id = str(member.organization_id)
        team_id = str(user.team_id) if user.team_id else None
        rows = await db.execute(
            text(
                f"SELECT id, name FROM projects WHERE organization_id = :org AND {base} "
                "AND (team_id = :team OR (team_id IS NULL AND created_by = :uid)) "
                "ORDER BY created_at DESC LIMIT 20"
            ),
            {"org": org_id, "team": team_id, "uid": str(user.id)},
        )
    return [ProjectRef(id=str(r.id), name=r.name) for r in rows]


@router.post("/complete")
async def chat_complete(
    body: ChatRequest,
    user: User | None = Depends(optional_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
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

        # 생성·기타는 교통정리(오케스트레이터)로 — 관리는 위에서 이미 처리됨.
        # 생성=슬롯필링(되묻기/트리거), advise/미등록=result None → 아래 CLIO 폴백.
        sub_req = SubagentRequest(
            messages=body.messages,
            session_id=body.session_id,
            user_id=str(user.id) if user else None,
            context_ad_id=body.context_ad_id,
            improve_context=body.improve_context,
            product_image_temp_key=body.product_image_temp_key,
            brand_logo_s3_key=body.brand_logo_s3_key,
            skip_asset_prompt=body.skip_asset_prompt,
        )

        async def _project_provider() -> list[ProjectRef]:
            return await _get_user_projects(user, db) if user else []

        try:
            _intent, result = await _get_orchestrator().run_turn(
                sub_req, project_provider=_project_provider
            )
        except Exception as exc:  # noqa: BLE001 — 라우팅 실패는 CLIO로 폴백(채팅 안 끊김)
            print(f"[chat] orchestrator error: {exc!r}")
            result = None
        if result is not None:
            for ev in _subagent_sse_events(result):
                yield ev
            yield 'data: {"done": true}\n\n'
            return

        # 그 외(advise/미등록)는 CLIO(OpenAI)
        clio_meta = {"source": "clio", "label": "CLIO", "engine": "OpenAI"}
        yield _sse({"meta": clio_meta})

        oai_messages = [{"role": "system", "content": _CLIO_SYSTEM}]
        for m in body.messages:
            oai_messages.append({
                "role": "user" if m.role == "user" else "assistant",
                "content": m.content,
            })

        try:
            stream = await _get_clio_client().chat.completions.create(
                model=getattr(settings, "chat_model", "gpt-4o-mini"),
                messages=oai_messages,
                stream=True,
            )
            async for chunk in stream:
                text = chunk.choices[0].delta.content or ""
                if text:
                    yield _sse({"token": text})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"token": f"CLIO 응답 중 문제가 발생했어요: {exc}"})

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
