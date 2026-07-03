import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant.improve_context import improve_gen_data_for_simulation
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
from core.tracing import make_trace_config
from domain.chat import history, result_callback, widgets
from domain.chat.loop_state import MAX_LOOP, get_loop_state
from domain.management.assistant.history import record_feedback  # RAG 피드백 적재(/feedback)
from tools.storage.s3 import download_bytes, upload_bytes

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from domain.management.assistant.memory_store import ManagementMemory

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

_memory = None  # 세션 넘는 장기기억(management memory_store) 싱글톤
_bg_tasks: set[asyncio.Task] = set()  # remember 백그라운드 — GC 방지 강참조
_clio_client = None  # 메모리 추출·요약용 OpenAI(gpt-4o-mini) 싱글톤


# ── 통합 채팅 에이전트(deepagents) — chat_complete의 실 경로 ──────────────────────
_unified_agent = None
_unified_agent_built = False

_LABEL_BY_SOURCE = {
    "simulation": "시뮬레이션",
    "generator": "생성",
    "management": "매니지먼트 어시스턴트",
    "deep-agent": "오케스트레이터",
    "orchestrator": "CLIO",
}


def _get_unified_agent() -> object | None:
    """통합 채팅 에이전트 싱글톤 — 빌드 1회(키 없으면 None, 캐시)."""
    global _unified_agent, _unified_agent_built  # noqa: PLW0603
    if not _unified_agent_built:
        try:
            from api.assistant.deep_agent_builder import build_unified_chat_agent  # noqa: PLC0415

            _unified_agent = build_unified_chat_agent(settings)
        except Exception as exc:  # noqa: BLE001 — 빌드 실패가 채팅 기동을 막지 않게
            print(f"[chat] unified agent build failed: {exc!r}")
            _unified_agent = None
        _unified_agent_built = True
    return _unified_agent


def _engine_label() -> str:
    provider = getattr(settings, "chat_orchestrator_provider", "openai")
    model = getattr(settings, "chat_orchestrator_model", "gpt-4o-mini")
    return f"{'Anthropic' if provider == 'anthropic' else 'OpenAI'} · {model}"


def _extract_text(content: object) -> str:
    """LLM 메시지 content에서 텍스트 추출 — Anthropic은 블록 list, OpenAI는 str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _to_lc_messages(messages: list) -> list:
    """ChatRequest 메시지 → LangChain 메시지(통합 에이전트 입력). 프론트가 풀히스토리 재전송."""
    from langchain_core.messages import AIMessage, HumanMessage  # noqa: PLC0415

    out: list = []
    for m in messages:
        out.append(
            AIMessage(content=m.content)
            if m.role == "assistant"
            else HumanMessage(content=m.content)
        )
    return out


def _assemble_chat_meta(state: dict, engine_label: str) -> dict:
    """통합 에이전트 최종 상태 → SSE meta(위젯·소스·인용·카드 신호). _state_to_result 규칙 이식."""
    sub = state.get("sub_meta") or {}
    mgmt = sub.get("management") or {}
    sim = sub.get("simulation") or {}
    gen = sub.get("generator") or {}
    clio = sub.get("clio") or {}
    source = (
        state.get("source")
        or mgmt.get("source")
        or sim.get("source")
        or gen.get("source")
        or clio.get("source")
        or "orchestrator"
    )
    citations = (
        (mgmt.get("citations") or [])
        + (sim.get("citations") or [])
        + (gen.get("citations") or [])
        + (clio.get("citations") or [])
    )
    meta: dict = {
        "source": source,
        "label": (
            mgmt.get("label")
            or sim.get("label")
            or gen.get("label")
            or clio.get("label")
            or _LABEL_BY_SOURCE.get(source, "CLIO")
        ),
        "engine": engine_label,
    }
    if citations:
        meta["citations"] = citations
    if mgmt.get("used_tools"):
        meta["used_tools"] = mgmt["used_tools"]
    if mgmt.get("suggested_action"):
        meta["suggested_action"] = mgmt["suggested_action"]
    if mgmt.get("evidence"):
        meta["evidence"] = mgmt["evidence"]
    if mgmt.get("campaigns"):
        meta["campaigns"] = mgmt["campaigns"]
    if state.get("widget"):
        meta["widget"] = state["widget"]
    return meta


def _get_memory() -> "ManagementMemory":
    """장기기억(ManagementMemory) 싱글톤 — recall/remember 공용."""
    global _memory
    if _memory is None:
        from domain.management.assistant.memory_store import build_memory_store  # noqa: PLC0415

        _memory = build_memory_store(settings)
    return _memory


def _memory_ids(body: ChatRequest, current_user: User) -> tuple[str | None, str | None]:
    """장기기억 네임스페이스 키 (tenant_id, user_id) — 본문 우선, 인증 유저 폴백."""
    user_id = body.user_id or (str(current_user.id) if getattr(current_user, "id", None) else None)
    tenant_id = body.organization_id or getattr(current_user, "organization_id", None)
    return (str(tenant_id) if tenant_id else None), user_id


async def _recall_memory_context(body: ChatRequest, query: str, current_user: User) -> str | None:
    """로그인 사용자의 세션 넘는 장기기억을 시맨틱 회수해 맥락 문자열로 포맷(없으면 None)."""
    tenant_id, user_id = _memory_ids(body, current_user)
    if not user_id:
        return None
    try:
        rows = await _get_memory().recall(tenant_id, user_id, query=query, limit=5)
    except Exception as exc:  # noqa: BLE001 — 회수 실패가 답변을 막지 않게
        print(f"[chat] recall error: {exc!r}")
        return None
    lines = [
        f"- {fact}" for r in rows if (fact := r.get("fact") or r.get("note") or r.get("summary"))
    ]
    if not lines:
        return None
    return "이 사용자의 장기기억(참고용):\n" + "\n".join(lines)


def _spawn_remember(body: ChatRequest, meta: dict | None, current_user: User) -> None:
    """행동 제안이 나온 턴을 장기기억에 적재(백그라운드, best-effort) — 과거 결정 요약 누적."""
    sa = meta.get("suggested_action") if isinstance(meta, dict) else None
    tenant_id, user_id = _memory_ids(body, current_user)
    if not user_id or not sa:
        return

    async def _run() -> None:
        try:
            key = f"action:{body.session_id}:{sa.get('action_type', 'unknown')}"
            fact = f"{sa.get('action_type', '')} 제안 — {str(sa.get('rationale', ''))[:120]}"
            await _get_memory().remember(
                tenant_id, user_id, key, {"fact": fact, "suggested_action": sa}
            )
        except Exception as exc:  # noqa: BLE001 — 적재 실패가 응답을 막지 않게
            print(f"[chat] remember error: {exc!r}")

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _get_clio_client() -> "AsyncOpenAI | None":
    """메모리 추출·요약용 OpenAI(gpt-4o-mini) 싱글톤. 키 없으면 None."""
    global _clio_client  # noqa: PLW0603
    if _clio_client is None:
        key = getattr(settings, "openai_api_key", None)
        if not key:
            return None
        from openai import AsyncOpenAI  # noqa: PLC0415

        _clio_client = AsyncOpenAI(api_key=key)
    return _clio_client


_EXTRACT_PROMPT = (
    "이 대화 턴에서 사용자에 대해 '세션을 넘어 기억할 가치가 있는 사실'이 있으면 추출하라.\n"
    "- semantic: 지속 선호·속성(목표·플랫폼·예산대·톤). dedup_key로 같은 속성은 갱신.\n"
    "- episodic: 한 일·결정(예: camp_1 일시중지 승인).\n"
    "- 단발 현황 질문('이번 달 예산?')·잡담·인사는 should_store=false.\n"
    "확신 없으면 should_store=false(과적재보다 누락이 안전).\n"
    'JSON만 출력: {{"should_store": bool, "kind": "semantic|episodic|none", '
    '"fact": "정규화된 한 문장 또는 null", "dedup_key": "pref:objective 같은 키 또는 null"}}\n\n'
    "[질문]\n{q}\n\n[답변]\n{a}"
)


async def _extract_memory(question: str, answer: str) -> dict | None:
    """턴에서 장기 저장할 사실을 LLM(gpt-4o-mini)으로 추출(M2). 저장 가치 없으면 None."""
    import json as _json  # noqa: PLC0415

    client = _get_clio_client()
    if client is None:
        return None
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": _EXTRACT_PROMPT.format(q=question[:300], a=answer[:300]),
                }
            ],
            temperature=0.0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        data = _json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001 — 추출 실패는 저장 안 함(보수)
        return None
    if not data.get("should_store") or not data.get("fact"):
        return None
    return {
        "kind": data.get("kind", "semantic"),
        "fact": data["fact"],
        "dedup_key": data.get("dedup_key"),
    }


async def _summarize_session(messages: list) -> str | None:
    """대화를 사용자 관심사·진행 중심으로 2문장 요약(M6 episodic). 실패는 None."""
    client = _get_clio_client()
    if client is None:
        return None
    convo = "\n".join(f"{m.role}: {m.content[:200]}" for m in messages[-10:])
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "다음 대화를 사용자 관심사·진행 상황 중심으로 2문장 이내 한국어로 "
                        "요약하라. 단발 사실 나열 말고 맥락 위주.\n\n" + convo
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=150,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _spawn_memory_capture(
    body: ChatRequest, question: str, answer: str, current_user: User
) -> None:
    """전 라우트 자동 LTM 캡처(백그라운드) — M2 사실 추출 + M6 세션 요약. 로그인 유저만."""
    tenant_id, user_id = _memory_ids(body, current_user)
    if not user_id:
        return

    async def _run() -> None:
        try:
            extracted = await _extract_memory(question, answer)
            if extracted:
                key = extracted.get("dedup_key") or uuid.uuid4().hex
                await _get_memory().remember(
                    tenant_id, user_id, key, {"kind": extracted["kind"], "fact": extracted["fact"]}
                )
            # M6 — 멀티턴(≥8 메시지)이 쌓이면 4메시지마다 세션 요약 upsert(비용 통제).
            if len(body.messages) >= 8 and len(body.messages) % 4 == 0:
                summ = await _summarize_session(body.messages)
                if summ:
                    await _get_memory().remember(
                        tenant_id,
                        user_id,
                        f"summary:{body.session_id}",
                        {"kind": "episodic", "fact": summ},
                    )
        except Exception as exc:  # noqa: BLE001 — 캡처 실패가 응답을 막지 않게
            print(f"[chat] memory capture error: {exc!r}")

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _cards_from_meta(meta: dict | None) -> list[dict]:
    """meta.suggested_action → 추천 조치 카드(EVIDENCE/RESULT/REVIEW/ACTIONBAR) 합성.

    행동 제안이 있을 때만 카드를 만든다(인용만 있는 답변은 기존 citations 칩으로 충분).
    management 단일 경로·deep 경로 모두 동일 meta 형식을 내므로 한 곳에서 합성한다.
    """
    if not isinstance(meta, dict) or not meta.get("suggested_action"):
        return []
    from domain.management.assistant.composer import compose_turn  # noqa: PLC0415
    from domain.management.assistant.contracts import (  # noqa: PLC0415
        AskResult,
        Citation,
        SuggestedAction,
    )

    sa = meta["suggested_action"]
    _cite_keys = ("kind", "source", "title", "trust", "source_url", "as_of")
    try:
        res = AskResult(
            answer="",
            citations=[
                Citation(**{k: c[k] for k in _cite_keys if k in c})
                for c in (meta.get("citations") or [])
            ],
            used_tools=list(meta.get("used_tools") or []),
            evidence=meta.get("evidence") or {},
            suggested_action=SuggestedAction(**sa),
        )
        env = compose_turn(res, turn_id=uuid.uuid4().hex[:12])
        return [c.model_dump(mode="json") for c in env.cards]
    except Exception as exc:  # noqa: BLE001 — 카드 합성 실패가 답변을 막지 않게
        print(f"[chat] cards build error: {exc!r}")
        return []


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
        # 진행 중 표시 — 느릴 수 있는 에이전트 호출 전에 스피너 트레이를 띄운다(T17).
        yield _sse("progress", progress={"label": "생각 중 🔄", "pct": None})
        # 세션 넘는 장기기억 회수 — 에이전트 맥락에 끼울 문자열(로그인 사용자만, best-effort).
        memory_context = await _recall_memory_context(body, last_message, current_user)

        # [생성결과] 구조화 콜백 — 프론트가 보낸 결과 신호는 에이전트 거치지 않고 결정론 처리(개선루프).
        if result_callback.is_result_callback(last_message):
            answer, meta = result_callback.handle(body.session_id, _engine_label())
            yield _sse("meta", meta=meta)
            for piece in _chunks(answer):
                yield _sse("text", token=piece)
            if meta.get("approval"):
                yield _sse("approval", approval=meta["approval"])
            await _persist(
                body.session_id, last_message, answer, meta, body.image_url, body.result_ref
            )
            yield _sse("done")
            return

        agent = _get_unified_agent()
        if agent is None:
            # 키 미설정 등 — 안내만(엔진 일원화, Gemini 폴백 없음).
            answer = "지금은 답변을 생성할 수 없어요. 잠시 후 다시 시도해주세요."
            meta = {"source": "orchestrator", "label": "CLIO", "engine": _engine_label()}
            yield _sse("meta", meta=meta)
            for piece in _chunks(answer):
                yield _sse("text", token=piece)
            await _persist(
                body.session_id, last_message, answer, meta, body.image_url, body.result_ref
            )
            yield _sse("done")
            return

        # 통합 에이전트 실시간 스트리밍 — 메인그래프 최종 답변 토큰을 흘리고, 최종 상태에서 위젯·메타 조립.
        tenant_id, user_id = _memory_ids(body, current_user)
        # 요청별 일회용 thread — 프론트가 매 턴 풀히스토리를 재전송하므로 누적 dedup 불필요(구 deep_agent와 동일).
        thread_id = f"chat-{body.session_id or 'anon'}-{uuid.uuid4().hex[:8]}"
        # LangSmith 표준 트레이스 — 루트 chat.assistant + 사용자/기능 필터용 메타(가이드 §4).
        config = make_trace_config(
            domain="chat",
            feature="assistant",
            user_id=user_id or "anonymous",
            login_id=getattr(current_user, "login_id", None),
            user_name=getattr(current_user, "name", None),
            role=getattr(current_user, "role", None),
            project_id=body.project_id,
            ad_id=body.context_ad_id,
            extra_metadata={"session_id": body.session_id, "org_id": tenant_id},
            extra_tags=["unified-agent"],
            configurable={"thread_id": thread_id},
        )
        initial = {
            "messages": _to_lc_messages(body.messages),
            "session_id": body.session_id,
            "user_id": user_id,
            "org_id": tenant_id,
            "project_id": body.project_id,
            "context_ad_id": body.context_ad_id,
            "memory_context": memory_context,
        }
        acc = ""
        state: dict = {}
        try:
            async for item in agent.astream(
                initial, config, stream_mode=["messages"], subgraphs=True
            ):
                if not (isinstance(item, tuple) and len(item) == 3):
                    continue
                ns, mode, data = item
                # 메인그래프(ns=()) 최종 답변 토큰만 — 서브에이전트 내부 토큰은 제외.
                if mode != "messages" or ns != ():
                    continue
                msg_chunk, _meta_info = data
                if "AIMessage" not in msg_chunk.__class__.__name__:
                    continue
                # 서브에이전트 tool이 부르는 내부 LLM(예: 매니지먼트 KB grade의
                # {"sufficient,rewrite})은 langsmith:nostream 태그로 표시 — ns=()로 새어도
                # 여기서 걸러 답변에 안 섞이게 한다(최종 답변만 스트리밍).
                if "langsmith:nostream" in ((_meta_info or {}).get("tags") or []):
                    continue
                text = _extract_text(getattr(msg_chunk, "content", ""))
                if text:
                    acc += text
                    yield _sse("text", token=text)
            snap = await agent.aget_state(config)
            state = snap.values or {}
        except Exception as exc:  # noqa: BLE001 — 스트리밍 실패해도 안내로 마무리.
            print(f"[chat] unified agent error: {exc!r}")
            if not acc:
                acc = "지금은 답변을 생성할 수 없어요. 잠시 후 다시 시도해주세요."
                yield _sse("text", token=acc)

        # 위젯·소스·카드 meta는 토큰 뒤 한 번(프론트는 meta가 text 뒤에 와도 독립 적용).
        meta = _assemble_chat_meta(state, _engine_label())
        cards = _cards_from_meta(meta)
        if cards:
            meta["cards"] = cards
        yield _sse("meta", meta=meta)
        if meta.get("approval"):
            yield _sse("approval", approval=meta["approval"])
        await _persist(body.session_id, last_message, acc, meta, body.image_url, body.result_ref)
        # 행동 제안이 나온 턴을 장기기억에 적재(백그라운드) — 다음 세션 recall에 반영.
        _spawn_remember(body, meta, current_user)
        # 전 라우트 자동 LTM 캡처(M2 사실추출 + M6 세션요약).
        _spawn_memory_capture(body, last_message, acc, current_user)
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
    # simulation_id가 있으면 시뮬 요약을 프리필한 IMPROVE 폼, 없으면 기존 CREATE 폼 폴백(하위호환).
    if body.action == "run_generator" and body.context:
        gen_data: dict | None = None
        sim_id = (body.context or {}).get("simulation_id")
        if sim_id:
            try:
                await assert_simulation_access(db, str(sim_id), current_user)
                gen_data = await improve_gen_data_for_simulation(str(sim_id))
            except HTTPException:
                gen_data = None  # 접근 불가/삭제 — CREATE 폴백
        if gen_data is None:
            gen_data = _gen_form_from_sim_context(body.context)
            ctx_answer = "토론에서 나온 개선 방향을 반영할게요. 아래에서 광고 정보를 확인·수정하고 다시 생성하세요."
        else:
            ctx_answer = (
                "시뮬 결과를 반영해 개선 시안을 만들게요. 아래에서 수정 요청을 적고 실행하세요."
            )
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
        # 수락 액션을 결정론으로 입력 위젯에 매핑(LLM 불필요) — rerun=시뮬 폼, run_generator=생성 폼.
        if body.action == "rerun_simulation":
            frag = widgets.sim_form(
                {"ad_title": None, "ad_content": "", "product_category": None, "ad_objective": None}
            )
            answer = "새 시안으로 다시 예측할게요. 아래에서 광고 정보를 확인·수정하고 실행하세요."
            label = "재시뮬"
        else:  # run_generator (개선 컨텍스트가 없는 경우)
            frag = widgets.gen_form(
                {
                    "product_name": None,
                    "product_description": None,
                    "target_audience": None,
                    "campaign_objective": None,
                }
            )
            answer = "개선 시안을 만들게요. 아래에서 생성 정보를 확인·수정하고 실행하세요."
            label = "개선 생성"
        meta = {
            "source": frag["source"],
            "label": label,
            "engine": _engine_label(),
            "widget": frag["widget"],
        }
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
