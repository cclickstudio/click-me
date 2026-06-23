# 채팅 엔드포인트 — 오케스트레이터(의도분류→서브에이전트)로 라우팅, advise는 CLIO 폴백
import asyncio
import json
import threading
from collections.abc import AsyncGenerator

import google.generativeai as genai
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant.contracts import ProjectRef, SubagentRequest
from api.assistant.orchestrator import Orchestrator
from api.assistant.wiring import build_assistant
from core.auth import get_current_user_optional
from core.config import settings
from core.db import get_db
from core.models import OrganizationMember, Project, User
from core.schemas import ChatRequest

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

# ── 오케스트레이터: 의도분류 → 도메인 서브에이전트(생성 슬롯형 / 관리 RAG), 그 외 CLIO ──
_orchestrator = None


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_assistant(settings)
    return _orchestrator


def _chunks(text: str, size: int = 24) -> list[str]:
    """긴 답변을 SSE 토큰처럼 잘게 — 스트리밍 느낌 유지."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


async def _list_user_projects(db: AsyncSession, user: User) -> list[ProjectRef]:
    """되묻기용 — 유저 조직의 프로젝트(id, name). org 단위 단순화(team 필터 생략)."""
    org_id = await db.scalar(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)
    )
    if not org_id:
        return []
    rows = (
        await db.execute(
            select(Project.id, Project.name)
            .where(Project.organization_id == org_id)
            .order_by(Project.created_at.desc())
        )
    ).all()
    return [ProjectRef(id=str(r.id), name=r.name) for r in rows]


@router.post("/complete")
async def chat_complete(
    body: ChatRequest,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    last_message = body.messages[-1].content if body.messages else ""
    gemini_history = [
        {"role": "user" if m.role == "user" else "model", "parts": [m.content]}
        for m in body.messages[:-1]
    ]

    req = SubagentRequest(
        messages=body.messages,
        session_id=body.session_id,
        user_id=str(user.id) if user else None,
        context_ad_id=body.context_ad_id,
    )

    async def _projects() -> list[ProjectRef]:
        if user is None:
            return []
        return await _list_user_projects(db, user)

    async def generate() -> AsyncGenerator[str, None]:
        # 1) 오케스트레이터 라우팅 — 생성/관리는 서브에이전트가 처리
        try:
            _intent, result = await _get_orchestrator().run_turn(req, project_provider=_projects)
        except Exception as exc:  # noqa: BLE001 — 실패해도 채팅은 끊지 않는다
            print(f"[chat] orchestrator error: {exc!r}")
            err_meta = {"source": "assistant", "label": "어시스턴트", "engine": "오케스트레이터"}
            yield f"data: {json.dumps({'meta': err_meta}, ensure_ascii=False)}\n\n"
            msg = "요청을 처리하는 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요."
            yield f"data: {json.dumps({'token': msg}, ensure_ascii=False)}\n\n"
            yield 'data: {"done": true}\n\n'
            return

        if result is not None:
            yield f"data: {json.dumps({'meta': result.meta}, ensure_ascii=False)}\n\n"
            for piece in _chunks(result.message):
                yield f"data: {json.dumps({'token': piece}, ensure_ascii=False)}\n\n"
            if result.started_event is not None:
                payload = {"started_event": result.started_event.model_dump()}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield 'data: {"done": true}\n\n'
            return

        # 2) advise(폴백) — 기존 CLIO(Gemini) 스트리밍
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
