import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import google.generativeai as genai
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant.contracts import SubagentRequest
from core.auth import optional_user, user_org_id
from core.config import settings
from core.db import get_db
from core.models import User
from core.schemas import ChatRequest
from domain.management.assistant.history import record_feedback, record_turn, summarize_feedback
from domain.management.assistant.memory_store import ManagementMemory, build_memory_store

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

# ── Deep Agent 오케스트레이터 — management·generate·advise 통합 라우팅 ──────
_orchestrator = None


def _get_orchestrator() -> Callable[[SubagentRequest], Awaitable[object]]:
    global _orchestrator  # noqa: PLW0603
    if _orchestrator is None:
        from api.assistant.wiring import build_deep_agent  # noqa: PLC0415

        _orchestrator = build_deep_agent(settings)
    return _orchestrator


def _chunks(text: str, size: int = 24) -> list[str]:
    """긴 답변을 SSE 토큰처럼 잘게 — 스트리밍 느낌 유지."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


_memory = None


def _get_memory() -> ManagementMemory:
    global _memory  # noqa: PLW0603
    if _memory is None:
        _memory = build_memory_store(settings)
    return _memory


async def _resolve_identity(user: User | None, db: AsyncSession) -> tuple[str | None, str | None]:
    """(tenant_id, user_id) — 로그인 상태면 org/user, 아니면 (None, None)=데모 네임스페이스."""
    if user is None:
        return None, None
    org = await user_org_id(user, db)
    return (str(org) if org else None), str(user.id)


def _format_memory(mems: list[dict]) -> str | None:
    """장기기억 dict들 → LLM 주입용 한 줄. 비어있으면 None."""
    notes = [m.get("note") for m in mems if m.get("note")]
    if not notes:
        return None
    return "[이전 대화에서 기억해둘 맥락: " + " · ".join(notes[:5]) + "]"


@router.post("/complete")
async def chat_complete(
    body: ChatRequest,
    user: User | None = Depends(optional_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # 식별자는 스트리밍 전에 해석(요청 db 사용) — 로그인 시 (org, user)로 장기기억 스코프.
    tenant_id, user_id = await _resolve_identity(user, db)
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
        # Deep Agent 오케스트레이터 — management/generate/advise 통합 라우팅.
        # advise(일반 질문)면 None 반환 → Gemini CLIO 폴백.
        try:
            _t0 = time.perf_counter()
            orch_result = await _get_orchestrator()(
                SubagentRequest(
                    messages=body.messages,
                    session_id=body.session_id or "",
                    context_ad_id=body.context_ad_id,
                    user_id=str(user.id) if user else None,
                )
            )
            _latency_ms = int((time.perf_counter() - _t0) * 1000)
        except Exception as exc:  # noqa: BLE001 — 오케스트레이터 실패 → CLIO 폴백
            print(f"[chat] orchestrator 실패, CLIO 폴백: {exc!r}")
            orch_result = None

        if orch_result is not None:
            # 오케스트레이터가 응답함 — management 또는 generator
            meta = orch_result.meta or {}
            yield f"data: {json.dumps({'meta': meta}, ensure_ascii=False)}\n\n"
            answer = orch_result.message
            for piece in _chunks(answer):
                yield f"data: {json.dumps({'token': piece}, ensure_ascii=False)}\n\n"

            # management 응답이면 기록·기억 적재
            if meta.get("source") == "management":
                thread_id = meta.get("thread_id") or f"mgmt-{body.session_id}"
                try:
                    await record_turn(
                        thread_id=thread_id,
                        question=last_message,
                        answer=answer,
                        model=getattr(settings, "management_assistant_model", "gpt-4o-mini"),
                        latency_ms=_latency_ms,
                        used_tools=meta.get("used_tools", []),
                        citations=[
                            {
                                "kind": c.get("kind", ""),
                                "source": c.get("source", ""),
                                "title": c.get("title", ""),
                            }
                            for c in meta.get("citations", [])
                        ],
                        suggested_action=meta.get("suggested_action"),
                        requires_approval=meta.get("requires_approval", False),
                        ad_id=body.context_ad_id,
                    )
                except Exception as rexc:  # noqa: BLE001
                    print(f"[chat] record_turn 실패(무시): {rexc!r}")
                try:
                    note = f"질문: {last_message[:60]}"
                    sa = meta.get("suggested_action")
                    if sa:
                        note += f" / 제안: {sa.get('action_type', '')}"
                    await _get_memory().remember(tenant_id, user_id, uuid4().hex, {"note": note})
                except Exception as mexc:  # noqa: BLE001
                    print(f"[chat] memory remember 실패(무시): {mexc!r}")

            yield 'data: {"done": true}\n\n'
            return

        # ADVISE — 기존 CLIO(Gemini)
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


@router.get("/feedback/summary")
async def chat_feedback_summary(limit: int = 20) -> dict:
    """RAG 품질 피드백 집계 — 좋아요율·실패유형 분해·최근 👎 리뷰 큐(개선 루프 가시화)."""
    return await summarize_feedback(limit=limit)


class ApproveActionRequest(BaseModel):
    """채팅 추천 조치(suggested_action)를 사람이 승인해 실행 경로로 보낸다(HITL)."""

    action_type: str  # PAUSE_CAMPAIGN / INCREASE_BUDGET / ACTIVATE_CAMPAIGN ...
    campaign_id: str | None = None
    thread_id: str | None = None  # mgmt-{session_id} — 관측 귀속용
    approver_id: str = "chat-user"  # 버튼 클릭 = 사람 승인


@router.post("/approve")
async def chat_approve(
    body: ApproveActionRequest, user: User | None = Depends(optional_user)
) -> dict:
    """채팅 추천 조치 승인 → 실행(HITL). 실행 모드는 settings가 봉인한다 —
    use_mock이면 MOCK(Meta 미접촉), 아니면 validate_only/live. 모든 write는 Executor 단일경로
    (멱등키·감사·Tier 재검증)로만 나간다 — 어시스턴트는 직접 writer를 부르지 않는다.
    """
    # 지연 import — executor 배선·실행모드 봉인은 management 라우터가 단일 소스(중복 배선 금지).
    from api.routers.management import _get_executor, _resolved_execution_mode  # noqa: PLC0415
    from domain.management.approval import approve, judge_tier  # noqa: PLC0415
    from domain.management.contracts.policy import (  # noqa: PLC0415
        APPROVAL_POLICY_VERSION,
        PROPOSAL_TTL_MINUTES,
    )
    from domain.management.contracts.schemas import (  # noqa: PLC0415
        ActionProposal,
        finalize_proposal,
    )

    now = datetime.now(UTC)
    campaign = body.campaign_id or "demo_campaign"
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id="demo_org",
            ad_account_id="act_demo",
            target_object_ids=(campaign,),
            action_type=body.action_type,
            action_tier=judge_tier(body.action_type),  # 정책 단일원천(TIER_POLICY)
            evidence_metrics={"source": "chat"},
            metrics_as_of=now,
            hypothesis="채팅 추천 조치 사용자 승인",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=0,
            budget_after_krw=0,
            max_total_spend_krw=0,
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )
    mode = _resolved_execution_mode()
    approver = str(user.id) if user is not None else body.approver_id  # 로그인 시 실제 승인자 귀속
    action = approve(proposal, approver, execution_mode=mode)
    result = await _get_executor().execute(action, proposal)
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    return {
        "status": status,  # success | rejected | ...
        "execution_mode": str(mode.value),
        "action_type": body.action_type,
        "campaign_id": campaign,
        "result": result.model_dump(mode="json"),
    }
