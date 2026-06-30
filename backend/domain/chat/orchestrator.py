# 채팅 오케스트레이터 — 최상위 입구는 CLIO(Deep Agent). 결정론 커맨드만 프리핸들러로 선처리
"""build_chat_orchestrator(settings) → ask(ChatTurn) -> ChatAnswer | None.

키+실모드면 결정론 커맨드(템플릿·리포트·배치·브랜드·개선루프)를 먼저 처리하고, 그 외 모든 추론·
라우팅은 CLIO(Deep Agent, deep_runner)가 전담한다. 도메인(시뮬·매니지·제너)은 CLIO의 도구다.
키 없으면 키워드 폴백(매니지만, 그 외 None → chat.py가 안내).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from core.assistant_contracts import SubagentRequest, SubagentResult
from core.schemas import ChatMessage
from domain.chat import history
from domain.chat.loop_state import MAX_LOOP, get_loop_state
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.simulation.assistant.tools import list_simulations as _list_simulations

# 매니지먼트로 라우팅하는 키워드(폴백 전용) — 풀모드는 CLIO가 도구 설명을 보고 스스로 판단한다.
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

# 입력 위젯 표시를 막지 않게 ltm 저장·프로필 추론을 백그라운드로 실행(결과는 다음 대화에 반영).
_bg_tasks: set[asyncio.Task] = set()


def _spawn_persist(project_id: str | None, mem_type: str, data: dict) -> None:
    """시뮬/생성 입력을 롱텀 메모리에 적재(백그라운드) — 템플릿 저장·맥락 회상에 쓰인다."""
    if not project_id or not data:
        return

    async def _run() -> None:
        try:
            await history.save_long_term_memory(project_id, mem_type, data)
            await history.infer_profile_from_execution_history(project_id)
        except Exception as exc:  # noqa: BLE001 — 영속 실패가 위젯/응답을 막지 않게
            print(f"[chat] persist error: {exc!r}")

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


@dataclass
class ChatTurn:
    """채팅 한 턴 입력 — 질문 + 직전 대화 + 광고 맥락."""

    question: str
    history: list[tuple[str, str]] = field(
        default_factory=list
    )  # (role, content), role=user|assistant
    ad_id: str | None = None
    session_id: str | None = None  # 개선 루프 상태 키(턴 간 보존)
    thread_id: str | None = None  # LangGraph 체크포인터 스레드 키(session_id와 동일)
    project_id: str | None = None  # 목록 조회 스코프(현재 프로젝트)
    # 세션 넘는 장기기억 회수 결과(api 계층이 recall→포맷해 주입). CLIO 맥락에 끼운다.
    memory_context: str | None = None


@dataclass
class ChatAnswer:
    """오케스트레이터 답변 — 본문 + 출처/근거 메타(SSE meta로 전달)."""

    answer: str
    meta: dict


def _format_ltm(ltm: list[dict]) -> str:
    """롱텀 메모리 목록 → 시스템 프롬프트에 앞붙일 컨텍스트 문자열(없으면 빈 문자열)."""
    if not ltm:
        return ""
    lines: list[str] = []
    for m in ltm:
        c = m.get("content") or {}
        if m.get("memory_type") == "sim_input":
            lines.append(
                f"- 최근 시뮬 입력: 제목 '{c.get('ad_title', '')}', "
                f"카테고리 '{c.get('product_category', '')}'"
            )
        elif m.get("memory_type") == "gen_input":
            lines.append(
                f"- 최근 생성 입력: 상품 '{c.get('product_name', '')}', "
                f"타깃 '{c.get('target_audience', '')}'"
            )
        elif m.get("memory_type") == "session_summary":
            lines.append(f"- 이전 대화 요약: {c.get('summary', '')}")
        else:
            lines.append(f"- 사용자 선호: {c}")
    return "이 프로젝트의 최근 맥락(참고용):\n" + "\n".join(lines) + "\n\n"


# 브랜드 프로파일 — 자동 업데이트 트리거 키워드(이 단어가 있을 때만 추출 LLM 호출).
_BRAND_CUES: frozenset[str] = frozenset(
    {"타겟", "타깃", "톤", "브랜드", "카테고리", "키워드", "느낌으로", "분위기"}
)
_BRAND_EXTRACT_SYSTEM = (
    "사용자 메시지에서 브랜드 설정을 추출하라(언급된 항목만, 없으면 빈 값).\n"
    "- brand_name: 브랜드/제품명\n"
    "- tone: 톤·매너(예: 친근한, 전문적인)\n"
    "- target_audience: 타깃 고객(예: 20-30대 여성)\n"
    "- product_category: 상품 카테고리\n"
    "- keywords: 핵심 키워드 목록\n"
    "명시되지 않은 항목은 비워라(지어내지 말 것)."
)


def _has_brand_cue(text: str) -> bool:
    return any(c in text for c in _BRAND_CUES)


# ── 템플릿(T12) 발화 감지 ──
def _is_template_list(text: str) -> bool:
    s = text.replace(" ", "")
    return "템플릿" in s and any(v in s for v in ("보여", "목록", "뭐있", "리스트", "내템플릿"))


def _template_load_name(text: str) -> str | None:
    """'여름 캠페인 템플릿으로 …' → '여름 캠페인'. 아니면 None."""
    if "템플릿으로" not in text.replace(" ", ""):
        return None
    idx = text.find("템플릿")
    if idx <= 0:
        return None
    name = text[:idx].strip().strip("'\"” ")
    return name[-30:] if name else None


def _is_template_save(text: str) -> bool:
    s = text.replace(" ", "")
    return "설정저장" in s or "템플릿저장" in s or ("저장" in s and "템플릿" in s)


def _quoted(text: str) -> str | None:
    """메시지에서 첫 따옴표 안 문자열을 뽑는다(정규식 없이)."""
    for q in ("'", '"', "“"):
        i = text.find(q)
        if i != -1:
            end = "”" if q == "“" else q
            j = text.find(end, i + 1)
            if j > i + 1:
                return text[i + 1 : j].strip()
    return None


def _template_save_name(text: str, content: dict, ttype: str) -> str:
    """저장할 템플릿 이름 — 따옴표 안 이름 우선, 없으면 내용/유형에서 유도."""
    q = _quoted(text)
    if q:
        return q[:80]
    base = content.get("ad_title") or content.get("product_name")
    if base:
        return str(base)[:80]
    return "시뮬 설정" if ttype == "sim" else "생성 설정"


# 리포트(T13) — '이번 달 시뮬 결과 PDF로 뽑아줘' 류 발화 단서.
def _is_report(text: str) -> bool:
    s = text.replace(" ", "")
    has_report = "리포트" in s or "보고서" in s or "pdf" in text.lower()
    return (
        has_report
        and any(v in s for v in ("뽑", "만들", "생성", "다운", "내려", "받"))
        or (has_report and "pdf" in text.lower())
    )


def _report_period(text: str) -> str:
    return "month" if ("이번달" in text.replace(" ", "") or "월간" in text) else "all"


# 배치 시뮬 — 새 광고 여러 버전을 한 번에 비교하려는 발화 단서(T11).
def _is_batch_sim(text: str) -> bool:
    t = text.replace(" ", "")
    if t.startswith("/비교"):  # 기존 시뮬 비교(T14)는 별도 처리 — 충돌 방지
        return False
    has_compare = "비교" in t or "버전" in t or "a/b" in text.lower() or "ab테스트" in t
    has_multi = "두광고" in t or "두개" in t or "여러" in t or "두버전" in t or "광고들" in t
    return has_compare and has_multi


def _is_brand_show(text: str) -> bool:
    """'브랜드 설정 보여줘' 류 — 현재 프로파일 출력 요청."""
    t = text.replace(" ", "")
    has_brand = "브랜드" in t and ("설정" in t or "프로파일" in t or "프로필" in t)
    return has_brand and any(v in t for v in ("보여", "뭐", "알려", "확인", "조회"))


def _format_brand(brand: dict | None) -> str:
    """브랜드 프로파일 → 시스템 프롬프트 앞 컨텍스트(없으면 빈 문자열)."""
    if not brand:
        return ""
    parts = []
    if brand.get("brand_name"):
        parts.append(f"브랜드 {brand['brand_name']}")
    if brand.get("tone"):
        parts.append(f"톤 {brand['tone']}")
    if brand.get("target_audience"):
        parts.append(f"타깃 {brand['target_audience']}")
    if brand.get("product_category"):
        parts.append(f"카테고리 {brand['product_category']}")
    if brand.get("keywords"):
        parts.append(f"키워드 {', '.join(brand['keywords'])}")
    if not parts:
        return ""
    return "이 프로젝트의 브랜드 설정(참고용): " + " · ".join(parts) + "\n\n"


def _brand_show_text(brand: dict | None) -> str:
    """'브랜드 설정 보여줘' 응답 텍스트."""
    if not brand or not any(brand.get(k) for k in brand):
        return "아직 저장된 브랜드 설정이 없어요. '타겟은 20대 여성이야'처럼 알려주시면 기억할게요."
    lines = ["현재 브랜드 설정이에요."]
    labels = {
        "brand_name": "브랜드명",
        "tone": "톤",
        "target_audience": "타깃",
        "product_category": "카테고리",
        "keywords": "키워드",
    }
    for k, label in labels.items():
        v = brand.get(k)
        if v:
            lines.append(f"- {label}: {', '.join(v) if isinstance(v, list) else v}")
    return "\n".join(lines)


def _is_management(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _MGMT_KEYWORDS)


def _mgmt_answer(res: AskResult) -> str:
    """AskResult → 사용자 답변. 행동 제안이 있으면 승인 안내를 덧붙인다."""
    answer = res.answer
    if res.suggested_action:
        sa = res.suggested_action
        gate = "사람 승인 필요" if sa.requires_approval else "낮은 위험"
        answer += f"\n\n추천 조치: {sa.action_type} ({gate}) — 실행은 승인 화면에서 확인하세요."
    return answer


def _mgmt_meta(res: AskResult) -> dict:
    """AskResult → SSE meta(출처·인용·승인 게이트). suggested_action/evidence는 추천 카드 생성용."""
    return {
        "source": "management",
        "label": "매니지먼트 어시스턴트",
        "engine": "OpenAI · 실측+KB",
        "citations": [
            {"kind": c.kind, "source": c.source, "title": c.title} for c in res.citations
        ],
        "used_tools": res.used_tools,
        "requires_approval": res.requires_approval,
        "thread_id": res.thread_id,
        # api 계층(chat.py)이 이 값으로 meta.cards(RESULT/REVIEW/ACTIONBAR)를 합성한다.
        "suggested_action": (res.suggested_action.model_dump() if res.suggested_action else None),
        "evidence": res.evidence,
    }


def build_chat_orchestrator(
    settings,
    deep_runner: Callable[[SubagentRequest], Awaitable[SubagentResult | None]] | None = None,
) -> Callable[[ChatTurn], Awaitable[ChatAnswer | None]]:
    """오케스트레이터 진입점. 키+실모드면 결정론 커맨드 선처리 → CLIO 직결, 아니면 키워드 폴백.

    deep_runner(포트) — 최상위 CLIO(Deep Agent) 도구루프 실행기. api 계층이 조립해 주입
    (domain→api 역의존 회피). None이면 키워드 매니지 폴백.
    """
    api_key = getattr(settings, "openai_api_key", None)
    use_mock = getattr(settings, "use_mock", True)
    mgmt = build_management_agent(settings)  # 폴백/풀모드 자동 분기(같은 게이트)

    # ── 폴백 — 키워드로 매니지 질문만 라우팅, 일반 대화는 None(라우터가 안내) ──
    if use_mock or not api_key or deep_runner is None:

        async def _ask_fallback(turn: ChatTurn) -> ChatAnswer | None:
            if not _is_management(turn.question):
                return None
            res = await mgmt(AskRequest(question=turn.question, ad_id=turn.ad_id))
            return ChatAnswer(answer=_mgmt_answer(res), meta=_mgmt_meta(res))

        return _ask_fallback

    # ── 풀모드 — 결정론 커맨드 프리핸들러 → CLIO(Deep Agent) 직결 ──
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415
    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    from pydantic import BaseModel  # noqa: PLC0415

    provider = getattr(settings, "chat_orchestrator_provider", "openai")
    model_name = getattr(settings, "chat_orchestrator_model", "gpt-4o-mini")
    engine_label = f"{'Anthropic' if provider == 'anthropic' else 'OpenAI'} · {model_name}"
    # 브랜드 설정 추출용 경량 모델(결정론) — CLIO 답변 엔진과 분리.
    fast_llm = ChatOpenAI(
        model=getattr(settings, "chat_classify_model", "gpt-4o-mini"),
        temperature=0,
        api_key=settings.openai_api_key,
    )

    class _BrandExtract(BaseModel):
        brand_name: str = ""
        tone: str = ""
        target_audience: str = ""
        product_category: str = ""
        keywords: list[str] = []

    async def _gen_result(turn: ChatTurn) -> ChatAnswer:
        """위젯이 보낸 생성 결과 보고('[생성결과]…') → 새 시안 재시뮬 제안(개선 루프).

        실행은 하지 않고 제안만 한다.
        """
        loop = get_loop_state(turn.session_id)
        loop.phase = "gen_done"
        if loop.loop_count >= MAX_LOOP:
            return ChatAnswer(
                f"개선 루프 {loop.loop_count}/{MAX_LOOP}턴을 다 돌았어요. 새 시안까지 충분히 "
                "다듬었으니, 더 개선하려면 새 채팅에서 시작해 주세요.",
                {
                    "source": "generator",
                    "label": "개선 루프 완료",
                    "engine": engine_label,
                    "loop_done": True,
                },
            )
        return ChatAnswer(
            "새 시안이 준비됐네요. 새 시안으로 반응을 다시 예측해볼까요?",
            {
                "source": "generator",
                "label": "결과 분석 · 재시뮬 제안",
                "engine": engine_label,
                "suggest": "simulation",
                "approval": {
                    "action": "rerun_simulation",
                    "label": "새 시안으로 재시뮬",
                    "reasons": loop.weak_reasons,
                },
            },
        )

    async def _ask_full(turn: ChatTurn) -> ChatAnswer:
        sid = turn.session_id
        q = (turn.question or "").strip()

        # 위젯이 보낸 생성결과 보고 — 개선 루프(결정론).
        if q.startswith("[생성결과]"):
            return await _gen_result(turn)
        # /비교 명령어 — 시뮬 목록을 다중 선택(compare) 모드로 띄운다(T14).
        if q.replace(" ", "").startswith("/비교"):
            items = await _list_simulations(turn.project_id or "", limit=5)
            answer = (
                "비교할 시뮬레이션을 2개 선택하세요."
                if items
                else "비교할 시뮬레이션이 아직 없어요."
            )
            return ChatAnswer(
                answer=answer,
                meta={
                    "source": "simulation",
                    "label": "시뮬레이션 비교",
                    "widget": {"type": "sim_list", "mode": "compare", "data": {"items": items}},
                },
            )
        # 리포트 요청 — 다운로드 버튼 위젯을 띄운다(실제 파일은 /api/chat/report).
        if _is_report(q):
            period = _report_period(q)
            return ChatAnswer(
                answer="리포트를 준비했어요. 아래 버튼으로 다운로드하세요.",
                meta={
                    "source": "simulation",
                    "label": "리포트",
                    "widget": {
                        "type": "report_ready",
                        "data": {"project_id": turn.project_id, "period": period},
                    },
                },
            )
        _tpl_meta = {"source": "simulation", "label": "템플릿", "engine": engine_label}
        # 템플릿 목록 — 저장된 설정 보여주기.
        if _is_template_list(q):
            tpls = await history.list_templates(turn.project_id)
            if not tpls:
                ans = "아직 저장된 템플릿이 없어요. '이 설정 저장해줘'로 만들 수 있어요."
            else:
                ans = "저장된 템플릿이에요.\n" + "\n".join(
                    f"- {t['name']} ({'시뮬' if t['template_type'] == 'sim' else '생성'})"
                    for t in tpls
                )
            return ChatAnswer(answer=ans, meta=_tpl_meta)
        # 템플릿으로 실행 — 이름으로 찾아 폼 초기값 채우기.
        _load_name = _template_load_name(q)
        if _load_name:
            tpl = await history.get_template_by_name(turn.project_id, _load_name)
            if tpl is None:
                return ChatAnswer(
                    answer=(
                        f"'{_load_name}' 템플릿을 찾지 못했어요. '내 템플릿 보여줘'로 확인해보세요."
                    ),
                    meta=_tpl_meta,
                )
            wtype = "sim_form" if tpl["template_type"] == "sim" else "gen_form"
            return ChatAnswer(
                answer=f"'{tpl['name']}' 템플릿으로 채웠어요. 확인·수정 후 실행하세요.",
                meta={
                    "source": "simulation" if tpl["template_type"] == "sim" else "generator",
                    "label": "템플릿 불러오기",
                    "widget": {"type": wtype, "data": tpl["content"]},
                },
            )
        # 설정 저장 — 최근 시뮬/생성 입력을 템플릿으로 보관.
        if _is_template_save(q):
            recent = await history.get_long_term_memory(turn.project_id, limit=5)
            latest = next(
                (m for m in recent if m.get("memory_type") in ("sim_input", "gen_input")), None
            )
            if latest is None:
                return ChatAnswer(
                    answer="저장할 설정이 없어요. 먼저 시뮬레이션이나 생성을 한 번 진행해주세요.",
                    meta=_tpl_meta,
                )
            ttype = "sim" if latest["memory_type"] == "sim_input" else "gen"
            name = _template_save_name(q, latest.get("content") or {}, ttype)
            saved = await history.save_template(
                turn.project_id, name, ttype, latest.get("content") or {}
            )
            ok_msg = (
                f"'{name}' 템플릿으로 저장했어요. "
                f"다음엔 '{name} 템플릿으로 시뮬 돌려줘'처럼 쓰세요."
            )
            return ChatAnswer(
                answer=ok_msg if saved else "템플릿 저장에 실패했어요. 잠시 후 다시 시도해주세요.",
                meta=_tpl_meta,
            )
        # 배치 시뮬 요청 — 바로 입력 위젯을 띄운다(광고 2개 비교).
        if _is_batch_sim(q):
            return ChatAnswer(
                answer="여러 광고를 한 번에 비교할게요. 아래에 광고 2개를 입력하고 실행하세요.",
                meta={
                    "source": "simulation",
                    "label": "배치 시뮬",
                    "widget": {"type": "batch_sim_form"},
                },
            )
        # 브랜드 설정 조회 요청 — 바로 현재 프로파일을 출력.
        if _is_brand_show(q):
            brand = await history.get_brand_profile(turn.project_id)
            return ChatAnswer(
                answer=_brand_show_text(brand),
                meta={"source": "orchestrator", "label": "브랜드 설정", "engine": engine_label},
            )
        # 브랜드 단서가 있으면 발화에서 설정을 추출해 자동 업데이트(부분 upsert, 사이드이펙트).
        if turn.project_id and _has_brand_cue(q):
            try:
                be = await fast_llm.with_structured_output(_BrandExtract).ainvoke(
                    [SystemMessage(content=_BRAND_EXTRACT_SYSTEM), HumanMessage(content=q)]
                )
                await history.upsert_brand_profile(turn.project_id, be.model_dump())
            except Exception as exc:  # noqa: BLE001 — 추출 실패가 대화를 막지 않게
                print(f"[chat] brand extract error: {exc!r}")

        # ── 프로젝트 맥락(ltm·brand) 로드 → CLIO LLM 컨텍스트 preamble로 합친다 ──
        ltm = await history.search_long_term_memory(turn.project_id, turn.question, k=4)
        # session_summary는 매번 쌓이는 sim/gen_input에 밀려 top-k에서 빠질 수 있어 별도 보강.
        if not any(m.get("memory_type") == "session_summary" for m in ltm):
            summary_rows = await history.get_long_term_memory(
                turn.project_id, limit=1, memory_type="session_summary"
            )
            ltm = summary_rows + ltm
        brand = await history.get_brand_profile(turn.project_id)
        preamble = "".join(
            p
            for p in (turn.memory_context, _format_brand(brand), _format_ltm(ltm))
            if p
        )

        # ── CLIO(Deep Agent) 직결 — 도메인 라우팅·일반답·신호 위젯을 모두 전담 ──
        msgs = [ChatMessage(role=role, content=content) for role, content in turn.history]
        msgs.append(ChatMessage(role="user", content=turn.question))
        req = SubagentRequest(
            messages=msgs,
            session_id=sid or "",
            project_id=turn.project_id,
            context_ad_id=turn.ad_id,
            memory_context=preamble or None,
        )
        try:
            result: SubagentResult | None = await deep_runner(req)
        except Exception as exc:  # noqa: BLE001 — CLIO 실패가 대화를 끊지 않게 안내로 마무리
            print(f"[chat] deep_runner error: {exc!r}")
            result = None
        if result is None or not (result.message or "").strip():
            return ChatAnswer(
                "지금은 답변을 생성할 수 없어요. 잠시 후 다시 시도해주세요.",
                {"source": "orchestrator", "label": "CLIO", "engine": engine_label},
            )

        meta = dict(result.meta or {})
        meta.setdefault("source", "orchestrator")
        meta.setdefault("label", "CLIO")
        meta.setdefault("engine", engine_label)
        # 라우팅 로그(T20) — classify 없이 CLIO source로 대체.
        meta["routing"] = {"intent": meta.get("source"), "action": "ask", "confidence": "high"}
        meta = {**meta, "thread_id": turn.thread_id or sid, "session_id": sid}

        # 시뮬/생성 입력 폼을 띄웠으면 그 입력을 롱텀 메모리에 적재(템플릿 저장·맥락 회상 유지).
        widget = meta.get("widget") or {}
        if widget.get("type") == "sim_form":
            _spawn_persist(turn.project_id, "sim_input", widget.get("data") or {})
        elif widget.get("type") == "gen_form":
            _spawn_persist(turn.project_id, "gen_input", widget.get("data") or {})

        return ChatAnswer(answer=result.message, meta=meta)

    return _ask_full
