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
from domain.chat.loop_state import get_loop_state
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
async def chat_complete(body: ChatRequest) -> StreamingResponse:
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


# 개선 루프 수락 시 합성할 질문 — 오케스트레이터 run 분기를 재사용해 입력 위젯을 띄운다.
_APPROVE_PROMPTS: dict[str, str] = {
    "run_generator": "개선 시안 만들어줘",
    "rerun_simulation": "시뮬레이션 다시 돌려줘",
}


@router.post("/approve")
async def chat_approve(body: ApproveRequest) -> StreamingResponse:
    """개선 루프 수락 — 왕복 카운트를 올리고, 해당 액션의 입력 위젯을 스트리밍한다(HITL)."""
    loop = get_loop_state(body.session_id)
    if body.action == "run_generator":
        loop.loop_count += 1  # 시뮬→제너 왕복 1회 확정
        loop.phase = "gen_done"
    question = _APPROVE_PROMPTS.get(body.action, "개선 시안 만들어줘")

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


class BatchSimAd(BaseModel):
    ad_title: str | None = None
    ad_content: str
    product_category: str | None = None
    ad_objective: str | None = None


class BatchSimRequest(BaseModel):
    ads: list[BatchSimAd]
    project_id: str | None = None


@router.post("/sim-batch")
async def chat_sim_batch(body: BatchSimRequest) -> dict:
    """배치 시뮬 — 광고 여러 버전을 순차 실행(동시 금지 정책 준수)해 KPI를 나란히 반환(T11).

    경로는 명세(/api/simulations/batch) 대신 채팅 소유 경로로 둔다(채팅 위젯 전용).
    """
    from domain.simulation.assistant.tools import run_simulation  # noqa: PLC0415

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
async def append_widget_messages(body: AppendWidgetsRequest) -> dict:
    """단독 위젯 메시지(시뮬 결과·토론 stream·토론 요약 등)를 세션에 영속화 — 새로고침 복원용.

    프론트가 시뮬/토론 완료 시점에 결과·토론 위젯을 별도 어시스턴트 메시지로 남긴다.
    """
    items = [{"content": it.content, "meta": it.meta} for it in body.items]
    saved = await history.append_widget_messages(body.session_id, items)
    return {"messages": saved}


class PinRequest(BaseModel):
    pinned: bool = True


@router.patch("/messages/{message_id}/pin")
async def pin_chat_message(message_id: str, body: PinRequest) -> dict:
    """메시지 핀 토글(T19) — 세션 상단 고정 표시용."""
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
async def create_template(body: TemplateCreate) -> dict:
    """광고 설정 템플릿 저장(T12) — 같은 이름이면 갱신."""
    saved = await history.save_template(
        body.project_id, body.name, body.template_type, body.content
    )
    if saved is None:
        raise HTTPException(
            status_code=400, detail="템플릿을 저장할 수 없습니다(프로젝트·이름 확인)."
        )
    return saved


@router.get("/templates")
async def list_templates(project_id: str | None = None) -> dict:
    """프로젝트 템플릿 목록(T12)."""
    return {"templates": await history.list_templates(project_id)}


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


@router.get("/advice-usage")
async def advice_usage(project_id: str | None = None) -> dict:
    """비광고(일반 업무) 질문 사용량 — progress bar용(P12). 광고 질문은 무제한."""
    used = await history.count_advice_usage(project_id)
    return {"used": used, "limit": settings.chat_advice_usage_limit}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """세션의 메시지 내역."""
    return {"session_id": session_id, "messages": await history.get_messages(db, session_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """세션 삭제(메시지 CASCADE)."""
    return {"deleted": await history.delete_session(db, session_id)}


@router.get("/result-summary")
async def chat_result_summary(kind: str, id: str) -> dict:
    """채팅 결과 위젯·카드용 결과 요약 — kind=sim(4대 KPI)·gen(후보 요약). 기존 도구 재사용."""
    if kind == "sim":
        from domain.simulation.assistant.tools import fetch_simulation_result  # noqa: PLC0415

        return await fetch_simulation_result(id)
    if kind == "gen":
        from domain.generator.assistant.tools import fetch_generation_result  # noqa: PLC0415

        return await fetch_generation_result(id)
    raise HTTPException(status_code=400, detail="kind는 sim 또는 gen 이어야 합니다.")


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


@router.get("/kb-chunk")
async def get_kb_chunk(
    source: str, title: str | None = None, db: AsyncSession = Depends(get_db)
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
