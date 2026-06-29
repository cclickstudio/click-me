import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.access import (
    assert_generation_access,
    assert_message_access,
    assert_project_access,
    assert_session_access,
    assert_simulation_access,
)
from core.auth import get_current_user
from core.config import settings
from core.db import AsyncSessionLocal, get_db
from core.models import User
from core.schemas import ChatRequest
from domain.chat import history
from domain.chat.loop_state import MAX_LOOP, get_loop_state
from domain.chat.orchestrator import ChatTurn, build_chat_orchestrator
from domain.management.assistant.history import record_feedback  # RAG 피드백 적재(/feedback)
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


def _thread_id_for_session(session_id: str, compat_thread_id: str | None = None) -> str:
    """L2-2: 체크포인터 thread_id는 session_id로 고정하고, 구 thread_id 입력은 호환만 허용."""
    if compat_thread_id and compat_thread_id != session_id:
        print(f"[chat] thread_id ignored in favor of session_id: {compat_thread_id!r}")
    return session_id


def _chunks(text: str, size: int = 24) -> list[str]:
    """긴 답변을 SSE 토큰처럼 잘게 — 스트리밍 느낌 유지."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _sse(kind: str, **payload: object) -> str:
    """표준 SSE envelope — 모든 이벤트에 kind 이름표를 붙인다(meta·text·widget·approval·done)."""
    return f"data: {json.dumps({'kind': kind, **payload}, ensure_ascii=False)}\n\n"


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
async def chat_complete(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    if body.project_id:
        await assert_project_access(db, body.project_id, current_user)
    last_message = body.messages[-1].content if body.messages else ""

    async def generate() -> AsyncGenerator[str, None]:
        # 진행 중 표시 — 느릴 수 있는 오케스트레이터 호출 전에 스피너 트레이를 띄운다(T17).
        yield _sse("progress", progress={"label": "생각 중 🔄", "pct": None})
        # 오케스트레이터(OpenAI) 단일 경로 — classify → route → 도메인 서브에이전트/advise.
        try:
            orch = await _get_orchestrator()(
                ChatTurn(
                    question=last_message,
                    history=[(m.role, m.content) for m in body.messages[:-1]],
                    ad_id=body.context_ad_id,
                    session_id=body.session_id,
                    thread_id=_thread_id_for_session(body.session_id, body.thread_id),
                    project_id=body.project_id,
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

        yield _sse("meta", meta=meta)
        for piece in _chunks(answer):
            yield _sse("text", token=piece)
        # 개선 루프 HITL — 약한 결과면 meta.approval로 수락/거절 카드를 별도 이벤트로 보낸다.
        if isinstance(meta, dict) and meta.get("approval"):
            yield _sse("approval", approval=meta["approval"])
        await _persist(body.session_id, last_message, answer, meta, body.image_url, body.result_ref)
        yield _sse("done")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ApproveRequest(BaseModel):
    action: str  # run_generator | rerun_simulation
    session_id: str
    thread_id: str | None = None  # 호환 입력. 실제 체크포인터 키는 session_id.
    project_id: str | None = None
    # 개선 루프 컨텍스트 — 방금 시뮬한 광고({ad_title, ad_content, ad_objective, reasons}).
    # 있으면 LLM 추출(맥락 없는 합성 질문 → 엉뚱한 상품 환각)을 건너뛰고 실제 광고를 폼에 옮긴다.
    context: dict | None = None


# 개선 루프 수락 시 합성할 질문 — 오케스트레이터 run 분기를 재사용해 입력 위젯을 띄운다.
_APPROVE_PROMPTS: dict[str, str] = {
    "run_generator": "개선 시안 만들어줘",
    "rerun_simulation": "시뮬레이션 다시 돌려줘",
}


def _gen_form_from_sim_context(ctx: dict) -> dict:
    """시뮬→제너 개선 루프 — 방금 시뮬한 광고를 제너 입력값으로 옮긴다(상품 맥락 보존).

    합성 질문 '개선 시안 만들어줘'엔 상품 정보가 없어 LLM 추출이 엉뚱한 상품을 지어낸다.
    프론트가 직전 시뮬 광고를 context로 넘기면 그 광고를 그대로 폼 초기값으로 채운다.
    target_audience는 시뮬 입력에 없으므로 비워 사용자가 채우게 한다(환각 대신).
    """
    reasons = ctx.get("reasons") or []
    desc = (ctx.get("ad_content") or "").strip()
    if reasons:
        joined = " / ".join(str(r).strip() for r in reasons if str(r).strip())
        if joined:
            desc = f"{desc}\n\n개선 방향: {joined}".strip()
    return {
        "product_name": (ctx.get("ad_title") or "").strip(),
        "product_description": desc,
        "target_audience": (ctx.get("target_audience") or "").strip(),
        "campaign_objective": "conversion",
    }


@router.post("/approve")
async def chat_approve(
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """개선 루프 수락 — 왕복 카운트를 올리고, 해당 액션의 입력 위젯을 스트리밍한다(HITL)."""
    if body.project_id:
        await assert_project_access(db, body.project_id, current_user)
    loop = get_loop_state(body.session_id)
    question = _APPROVE_PROMPTS.get(body.action, "개선 시안 만들어줘")

    # 3턴 한도 — 도달 시 더 왕복하지 않고 안내만(authoritative 차단). 프론트가 버튼을 숨겨도
    # 구(舊) 위젯·재시도로 들어올 수 있어 서버에서 최종 차단한다.
    if loop.loop_count >= MAX_LOOP:
        loop.phase = "finished"
        done_answer = (
            f"개선 루프는 최대 {MAX_LOOP}턴까지 돌려요(현재 {loop.loop_count}/{MAX_LOOP}턴 완료). "
            "이미 충분히 다듬었어요 — 새 방향으로 가려면 새 채팅을 열어주세요."
        )
        done_meta = {
            "source": "orchestrator",
            "label": "개선 루프 완료",
            "engine": "OpenAI",
            "loop_done": True,
        }

        async def generate_done() -> AsyncGenerator[str, None]:
            yield _sse("meta", meta=done_meta)
            for piece in _chunks(done_answer):
                yield _sse("text", token=piece)
            await _persist(body.session_id, f"[수락] {question}", done_answer, done_meta)
            yield _sse("done")

        return StreamingResponse(
            generate_done(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if body.action == "run_generator":
        loop.loop_count += 1  # 시뮬→제너 왕복 1회 확정
        loop.phase = "gen_done"
    elif body.action == "rerun_simulation":
        loop.phase = "sim_done"

    # 개선 컨텍스트가 오면 LLM 추출(상품 환각)을 건너뛰고 직전 시뮬 광고를 그대로 폼에 옮긴다.
    if body.action == "run_generator" and body.context:
        gen_data = _gen_form_from_sim_context(body.context)
        ctx_answer = "토론에서 나온 개선 방향을 반영할게요. 아래에서 광고 정보를 확인·수정하고 다시 생성하세요."
        ctx_meta = {
            "source": "generator",
            "label": "개선 생성",
            "widget": {"type": "gen_form", "data": gen_data},
        }

        async def generate_ctx() -> AsyncGenerator[str, None]:
            yield _sse("meta", meta=ctx_meta)
            for piece in _chunks(ctx_answer):
                yield _sse("text", token=piece)
            await _persist(body.session_id, f"[수락] {question}", ctx_answer, ctx_meta)
            yield _sse("done")

        return StreamingResponse(
            generate_ctx(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def generate() -> AsyncGenerator[str, None]:
        try:
            orch = await _get_orchestrator()(
                ChatTurn(
                    question=question,
                    history=[],
                    session_id=body.session_id,
                    thread_id=_thread_id_for_session(body.session_id, body.thread_id),
                    project_id=body.project_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 — 실패해도 안내로 마무리
            print(f"[chat] approve orchestrator error: {exc!r}")
            orch = None

        if orch is not None:
            answer, meta = orch.answer, orch.meta
        else:
            answer = "지금은 진행할 수 없어요. 잠시 후 다시 시도해주세요."
            meta = {"source": "orchestrator", "label": "CLIO", "engine": "OpenAI"}

        yield _sse("meta", meta=meta)
        for piece in _chunks(answer):
            yield _sse("text", token=piece)
        await _persist(body.session_id, f"[수락] {question}", answer, meta)
        yield _sse("done")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/loop-state")
async def chat_loop_state(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """개선 루프 상태 — 프론트가 3턴 도달 시 '개선 시안 만들기' 제안을 숨기는 데 쓴다."""
    await assert_session_access(db, session_id, current_user)
    loop = get_loop_state(session_id)
    return {
        "loop_count": loop.loop_count,
        "max_loop": MAX_LOOP,
        "can_improve": loop.loop_count < MAX_LOOP,
        "phase": loop.phase,
    }


class BatchSimAd(BaseModel):
    ad_title: str | None = None
    ad_content: str
    product_category: str | None = None
    ad_objective: str | None = None


class BatchSimRequest(BaseModel):
    ads: list[BatchSimAd]
    project_id: str | None = None


@router.post("/sim-batch")
async def chat_sim_batch(
    body: BatchSimRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """배치 시뮬 — 광고 여러 버전을 순차 실행(동시 금지 정책 준수)해 KPI를 나란히 반환(T11).

    경로는 명세(/api/simulations/batch) 대신 채팅 소유 경로로 둔다(채팅 위젯 전용).
    """
    from domain.simulation.assistant.tools import run_simulation  # noqa: PLC0415

    if body.project_id:
        await assert_project_access(db, body.project_id, current_user)
    if not body.ads or len(body.ads) < 2:
        raise HTTPException(status_code=400, detail="비교할 광고를 2개 이상 입력하세요.")
    if len(body.ads) > 4:
        raise HTTPException(status_code=400, detail="배치 비교는 최대 4개까지 가능합니다.")
    results: list[dict] = []
    for ad in body.ads:  # 순차 실행 — 동시 시뮬 금지 정책 유지
        try:
            kpi = await run_simulation(
                ad_content=ad.ad_content,
                ad_title=ad.ad_title,
                product_category=ad.product_category,
                ad_objective=ad.ad_objective,
            )
            results.append({"ad_title": ad.ad_title or "광고", **kpi})
        except Exception as exc:  # noqa: BLE001 — 한 건 실패가 전체를 막지 않게
            print(f"[chat] batch sim error: {exc!r}")
            results.append({"ad_title": ad.ad_title or "광고", "error": "failed"})
    return {"results": results}


class WidgetItem(BaseModel):
    content: str = ""
    meta: dict | None = None


class AppendWidgetsRequest(BaseModel):
    session_id: str
    items: list[WidgetItem]


@router.post("/widget-messages")
async def append_widget_messages(
    body: AppendWidgetsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """단독 위젯 메시지(시뮬 결과·토론 stream·토론 요약 등)를 세션에 영속화 — 새로고침 복원용.

    프론트가 시뮬/토론 완료 시점에 결과·토론 위젯을 별도 어시스턴트 메시지로 남긴다.
    """
    await assert_session_access(db, body.session_id, current_user)
    items = [{"content": it.content, "meta": it.meta} for it in body.items]
    saved = await history.append_widget_messages(body.session_id, items)
    return {"messages": saved}


class PinRequest(BaseModel):
    pinned: bool = True


@router.patch("/messages/{message_id}/pin")
async def pin_chat_message(
    message_id: str,
    body: PinRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """메시지 핀 토글(T19) — 세션 상단 고정 표시용."""
    await assert_message_access(db, message_id, current_user)
    ok = await history.pin_message(message_id, body.pinned)
    if not ok:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    return {"id": message_id, "pinned": body.pinned}


@router.get("/report")
async def chat_report(project_id: str | None = None, period: str = "month") -> Response:
    """채팅 트리거 프로젝트 리포트 다운로드(T13) — PDF(Chromium) 또는 HTML 폴백."""
    from domain.chat.report import generate_project_report  # noqa: PLC0415

    data, media, filename = await generate_project_report(project_id, period)
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class TemplateCreate(BaseModel):
    project_id: str | None = None
    name: str
    template_type: str = "sim"  # sim | gen
    content: dict


@router.post("/templates")
async def create_template(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """광고 설정 템플릿 저장(T12) — 같은 이름이면 갱신."""
    if body.project_id:
        await assert_project_access(db, body.project_id, current_user)
    saved = await history.save_template(
        body.project_id, body.name, body.template_type, body.content
    )
    if saved is None:
        raise HTTPException(
            status_code=400, detail="템플릿을 저장할 수 없습니다(프로젝트·이름 확인)."
        )
    return saved


@router.get("/templates")
async def list_templates(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """프로젝트 템플릿 목록(T12)."""
    if project_id:
        await assert_project_access(db, project_id, current_user)
    return {"templates": await history.list_templates(project_id)}


class SessionCreate(BaseModel):
    project_id: str | None = None
    title: str | None = None


@router.post("/sessions")
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """새 채팅 세션 생성 — 프로젝트에 귀속."""
    if body.project_id:
        await assert_project_access(db, body.project_id, current_user)
    s = await history.create_session(db, body.project_id, body.title)
    return {
        "id": str(s.id),
        "title": s.title,
        "project_id": str(s.project_id) if s.project_id else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/sessions")
async def list_sessions(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """프로젝트의 채팅 세션 목록 — 최근 갱신 순."""
    if project_id:
        await assert_project_access(db, project_id, current_user)
    return {"sessions": await history.list_sessions(db, project_id)}


@router.get("/notifications")
async def list_notifications(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """미확인 채팅 알림(N5) — unread>0 세션 목록(플로팅 벨·배지용). 라우트 변경 시 폴링."""
    if project_id:
        await assert_project_access(db, project_id, current_user)
    return {"notifications": await history.list_notifications(db, project_id)}


@router.post("/sessions/{session_id}/read")
async def mark_session_read(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """세션 열람 처리(N5) — last_read_at 갱신. 이후 그 세션은 미확인에서 빠진다."""
    await assert_session_access(db, session_id, current_user)
    await history.mark_session_read(session_id)
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """세션의 메시지 내역."""
    await assert_session_access(db, session_id, current_user)
    return {"session_id": session_id, "messages": await history.get_messages(db, session_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """세션 삭제(메시지 CASCADE)."""
    await assert_session_access(db, session_id, current_user)
    return {"deleted": await history.delete_session(db, session_id)}


@router.get("/result-summary")
async def chat_result_summary(
    kind: str,
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """채팅 결과 위젯·카드용 결과 요약 — kind=sim(4대 KPI)·gen(후보 요약). 기존 도구 재사용."""
    if kind == "sim":
        from domain.simulation.assistant.tools import fetch_simulation_result  # noqa: PLC0415

        await assert_simulation_access(db, id, current_user)
        return await fetch_simulation_result(id)
    if kind == "gen":
        from domain.generator.assistant.tools import fetch_generation_result  # noqa: PLC0415

        await assert_generation_access(db, id, current_user)
        return await fetch_generation_result(id)
    raise HTTPException(status_code=400, detail="kind는 sim 또는 gen 이어야 합니다.")


@router.post("/image")
async def upload_chat_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
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


class FeedbackRequest(BaseModel):
    thread_id: str | None = None  # 채팅 세션 키(mgmt-{session_id})
    message_id: str | None = None
    question: str | None = None
    answer: str | None = None
    rating: int | None = None  # 1 좋아요 / -1 싫어요
    failure_type: str | None = None  # wrong_tool|stale_doc|hallucinated_number|missing_citation 등
    corrected_answer: str | None = None


@router.post("/feedback")
async def chat_feedback(
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
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


@router.get("/kb-chunk")
async def get_kb_chunk(
    source: str,
    title: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """P5 인용 칩 — 출처 파일(+섹션)로 KB 원문 청크를 조회해 펼침용으로 반환한다.

    4개 KB 테이블(시뮬·제너·매니지·CLIO)을 순회하며 source(+title) 매칭 1건을 돌려준다. 읽기 전용.
    """
    from sqlalchemy import select

    from core.models import (
        ClioKbChunk,
        GeneratorKbChunk,
        ManagementKbChunk,
        SimulationKbChunk,
    )

    for model in (SimulationKbChunk, GeneratorKbChunk, ManagementKbChunk, ClioKbChunk):
        stmt = select(model.chunk, model.title).where(model.source == source)
        if title:
            stmt = stmt.where(model.title == title)
        row = (await db.execute(stmt.limit(1))).first()
        if row:
            return {"source": source, "title": row[1], "chunk": row[0]}
    raise HTTPException(status_code=404, detail="해당 인용 원문을 찾을 수 없습니다.")


class KeywordRequest(BaseModel):
    product: str | None = None  # 제품·서비스명
    category: str | None = None  # 업종·카테고리
    target: str | None = None  # 타깃 고객
    copy_text: str | None = None  # 광고 카피·문구
    context: str | None = None  # 자유 맥락(폴백)


_KEYWORD_SYSTEM = (
    "당신은 SNS 광고 마케터입니다. 주어진 광고 맥락에 맞는 인스타그램·유튜브 등 "
    "SNS 노출에 효과적인 한국어 해시태그와 검색 키워드를 추천합니다. "
    "트렌디하되 맥락과 무관한 과장·낚시성 표현은 피하고, 실제 검색·도달에 쓸 수 있는 것만 고릅니다. "
    "반드시 JSON으로만 응답합니다."
)

_KEYWORD_USER_TEMPLATE = """\
다음 광고 맥락에 맞는 SNS 해시태그와 키워드를 추천하세요.

[광고 맥락]
{context}

아래 JSON 형식으로만 출력하세요.
- hashtags: '#'으로 시작하는 해시태그 12개 (공백 없이, 한국어 위주)
- keywords: '#' 없는 검색 키워드 6개

{{
  "hashtags": ["#키워드1", "#키워드2"],
  "keywords": ["키워드1", "키워드2"]
}}"""


@router.post("/keywords")
async def suggest_keywords(
    body: KeywordRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """F10 — 광고 맥락 기반 추천 해시태그·키워드(SNS 활용). gpt-4o-mini로 추출, 칩으로 복사."""
    from openai import AsyncOpenAI

    from tools.utils import safe_json_loads

    parts = [
        f"제품·서비스: {body.product.strip()}" if body.product and body.product.strip() else "",
        f"업종·카테고리: {body.category.strip()}"
        if body.category and body.category.strip()
        else "",
        f"타깃 고객: {body.target.strip()}" if body.target and body.target.strip() else "",
        f"광고 카피: {body.copy_text.strip()}" if body.copy_text and body.copy_text.strip() else "",
        f"추가 맥락: {body.context.strip()}" if body.context and body.context.strip() else "",
    ]
    context = "\n".join(p for p in parts if p)
    if not context:
        raise HTTPException(
            status_code=400, detail="제품·카테고리·타깃·카피 중 하나는 입력해 주세요."
        )

    key = getattr(settings, "openai_api_key", None)
    if not key:
        raise HTTPException(status_code=503, detail="키워드 추천에 필요한 OpenAI 키가 없습니다.")

    try:
        client = AsyncOpenAI(api_key=key, timeout=30.0)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            messages=[
                {"role": "system", "content": _KEYWORD_SYSTEM},
                {"role": "user", "content": _KEYWORD_USER_TEMPLATE.format(context=context)},
            ],
            response_format={"type": "json_object"},
        )
        data = safe_json_loads(resp.choices[0].message.content)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"키워드 추천 생성에 실패했어요: {e}") from e

    def _clean(items: object, prefix: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        if isinstance(items, list):
            for it in items:
                s = str(it).strip()
                if not s:
                    continue
                if prefix == "#":
                    s = "#" + s.lstrip("#").replace(" ", "")
                if s in seen:
                    continue
                seen.add(s)
                out.append(s)
        return out

    hashtags = _clean(data.get("hashtags") if isinstance(data, dict) else None, "#")
    keywords = _clean(data.get("keywords") if isinstance(data, dict) else None, "")
    if not hashtags and not keywords:
        raise HTTPException(
            status_code=502, detail="키워드를 만들지 못했어요. 맥락을 더 구체적으로 적어 주세요."
        )
    return {"hashtags": hashtags, "keywords": keywords}
