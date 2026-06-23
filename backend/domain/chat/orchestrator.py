# 채팅 오케스트레이터 — 매니지/시뮬/생성 서브에이전트를 도구로 부르는 LLM 라우터
"""build_chat_orchestrator(settings) → ask(ChatTurn) -> ChatAnswer | None.

키+실모드면 classify_intent → route → 도메인 서브에이전트(매니지·시뮬·생성) 또는 advise(일반 조언).
아니면 키워드 폴백(매니지만 처리, 그 외 None → chat.py가 기존 CLIO(Gemini)로 답).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from core.assistant import AssistantRequest
from domain.generator.assistant.agent import build_generator_agent
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.simulation.assistant.agent import build_simulation_agent

# 매니지먼트로 라우팅하는 키워드(폴백 전용) — 풀모드는 LLM이 도구 설명을 보고 스스로 판단한다.
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

# classify_intent 분류 프롬프트 — 질문을 도메인으로 라우팅(팀 구조: classify → route).
_CLASSIFY_SYSTEM = (
    "사용자 질문을 한 도메인으로 분류하라.\n"
    "- management: 집행된 광고의 성과·예산·소진·CTR·ROAS·캠페인 관리\n"
    "- simulation: 집행 전 시뮬레이션 결과·구매의도·클릭의향률·신뢰도·거부율·KPI 정의\n"
    "- generator: 광고 생성·카피 전략·시안·작성 원칙\n"
    "- advise: 그 외 일반 광고 전략·아이디어\n"
    "질문·조회는 action=ask, 시뮬/생성을 실제 실행·돌려달라는 요청은 action=run으로 분류하라.\n"
    "action=run이고 광고 카피·문구가 질문에 있으면 ad_content로 추출하라.\n"
    "결과 ID(시뮬/생성 식별자)가 질문에 있으면 context_id로 함께 추출하라."
)

# advise(일반 조언) 프롬프트 — 도메인 도구 없이 직접 답.
_ADVISE_SYSTEM = (
    "너는 ClickMe의 수석 광고 전략 AI 어드바이저 CLIO다. 한국어로 간결하게 답한다.\n"
    "일반 광고 전략·해석·아이디어 질문에 도구 없이 직접 답한다. 문장 끝에 콜론을 쓰지 말 것."
)

# 생성 실행 입력 추출 프롬프트 — 사용자 요청에서 생성 파라미터 뽑기.
_GEN_EXTRACT_SYSTEM = (
    "사용자의 광고 생성 요청에서 입력을 추출하라.\n"
    "- product_name: 상품·서비스 이름\n"
    "- product_description: 상품 설명·특징\n"
    "- target_audience: 타깃 고객\n"
    "- campaign_objective: 캠페인 목표(기본 conversion)\n"
    "명시되지 않은 항목은 요청 내용으로 합리적으로 채워라."
)


@dataclass
class ChatTurn:
    """채팅 한 턴 입력 — 질문 + 직전 대화 + 광고 맥락."""

    question: str
    history: list[tuple[str, str]] = field(
        default_factory=list
    )  # (role, content), role=user|assistant
    ad_id: str | None = None


@dataclass
class ChatAnswer:
    """오케스트레이터 답변 — 본문 + 출처/근거 메타(SSE meta로 전달)."""

    answer: str
    meta: dict


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
    """AskResult → SSE meta(출처·인용·승인 게이트)."""
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
    }


def _assistant_meta(res, source: str, label: str) -> dict:
    """AssistantResult → SSE meta(출처·인용). 공통 계약 서브에이전트(시뮬·생성) 공용."""
    return {
        "source": source,
        "label": label,
        "engine": "OpenAI · 결과+KB",
        "citations": [
            {"kind": c.kind, "source": c.source, "title": c.title} for c in res.citations
        ],
        "used_tools": res.used_tools,
    }


def _format_sim_run(ev: dict) -> str:
    """run_simulation 결과 → 한국어 4대 KPI 요약."""
    rid = str(ev.get("run_id") or "")[:8]
    lines = [f"시뮬레이션을 돌렸어요 (run_id {rid}, 표본 {ev.get('effective_n')}명)."]
    cir = ev.get("click_intent_rate")
    if cir is not None:
        lo = (ev.get("ci_low") or 0) * 100
        hi = (ev.get("ci_high") or 0) * 100
        lines.append(f"· 클릭 의향률 {cir * 100:.1f}% [{lo:.0f}~{hi:.0f}%]")
    if ev.get("purchase_intent") is not None:
        lines.append(f"· 구매의도 {ev['purchase_intent']:.2f}/5")
    if ev.get("trust_avg") is not None:
        lines.append(f"· 신뢰도 {ev['trust_avg']:.2f}/5")
    if ev.get("rejection_rate") is not None:
        lines.append(f"· 거부율 {ev['rejection_rate'] * 100:.1f}%")
    return "\n".join(lines)


def build_chat_orchestrator(settings) -> Callable[[ChatTurn], Awaitable[ChatAnswer | None]]:
    """오케스트레이터 진입점. 키+실모드면 classify → route 그래프, 아니면 키워드 폴백."""
    api_key = getattr(settings, "openai_api_key", None)
    use_mock = getattr(settings, "use_mock", True)
    mgmt = build_management_agent(settings)  # 폴백/풀모드 자동 분기(같은 게이트)

    # ── 폴백 — 키워드로 매니지 질문만 라우팅, 일반 대화는 None(라우터가 Gemini로) ──
    if use_mock or not api_key:

        async def _ask_fallback(turn: ChatTurn) -> ChatAnswer | None:
            if not _is_management(turn.question):
                return None
            res = await mgmt(AskRequest(question=turn.question, ad_id=turn.ad_id))
            return ChatAnswer(answer=_mgmt_answer(res), meta=_mgmt_meta(res))

        return _ask_fallback

    # ── 풀모드 — classify_intent → route → 도메인 서브에이전트 / advise ──
    from typing import Literal, TypedDict  # noqa: PLC0415

    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415 — 키 있을 때만
    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415
    from pydantic import BaseModel  # noqa: PLC0415

    model_name = getattr(settings, "chat_orchestrator_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.2, api_key=api_key)
    sim = build_simulation_agent(settings)  # 시뮬 서브에이전트(폴백/풀모드 자동)
    gen = build_generator_agent(settings)  # 생성 서브에이전트(폴백/풀모드 자동)

    # classify_intent 출력 스키마 — 도메인 분류 + 결과 식별자 추출.
    class _Intent(BaseModel):
        intent: Literal["management", "simulation", "generator", "advise"]
        action: Literal["ask", "run"] = "ask"
        context_id: str | None = None
        ad_content: str | None = None

    # 생성 실행 입력 추출 스키마 — generator_node에서 question으로부터 채운다.
    class _GenInput(BaseModel):
        product_name: str = ""
        product_description: str = ""
        target_audience: str = ""
        campaign_objective: str = "conversion"

    classifier = llm.with_structured_output(_Intent)

    # 그래프 상태 — 메시지 누적이 아니라 분류→답변 1패스. 노드엔 어노테이트하지 않는다.
    class _State(TypedDict, total=False):
        question: str
        intent: str
        action: str
        context_id: str | None
        ad_content: str | None
        answer: str
        meta: dict

    async def classify(state) -> dict:
        res = await classifier.ainvoke(
            [SystemMessage(content=_CLASSIFY_SYSTEM), HumanMessage(content=state["question"])]
        )
        return {
            "intent": res.intent,
            "action": res.action,
            "context_id": res.context_id,
            "ad_content": res.ad_content,
        }

    async def management_node(state) -> dict:
        res = await mgmt(
            AskRequest(question=state["question"], campaign_id=state.get("context_id"))
        )
        return {"answer": _mgmt_answer(res), "meta": _mgmt_meta(res)}

    async def simulation_node(state) -> dict:
        if state.get("action") == "run":
            from domain.simulation.assistant.tools import run_simulation  # noqa: PLC0415

            ev = await run_simulation(ad_content=state.get("ad_content") or state["question"])
            return {
                "answer": _format_sim_run(ev),
                "meta": {
                    "source": "simulation",
                    "label": "시뮬레이션 실행",
                    "engine": "Gemini · 실행",
                },
            }
        res = await sim(
            AssistantRequest(question=state["question"], context_id=state.get("context_id"))
        )
        return {
            "answer": res.answer,
            "meta": _assistant_meta(res, "simulation", "시뮬레이션 어시스턴트"),
        }

    async def generator_node(state) -> dict:
        if state.get("action") == "run":
            extractor = llm.with_structured_output(_GenInput)
            gi = await extractor.ainvoke(
                [
                    SystemMessage(content=_GEN_EXTRACT_SYSTEM),
                    HumanMessage(content=state["question"]),
                ]
            )
            from domain.generator.assistant.tools import run_generation  # noqa: PLC0415

            ev = await run_generation(
                product_name=gi.product_name,
                product_description=gi.product_description,
                target_audience=gi.target_audience,
                campaign_objective=gi.campaign_objective,
            )
            gid = str(ev.get("generation_id") or "")[:8]
            return {
                "answer": f"광고 시안 생성을 시작했어요 (generation_id {gid})."
                " 완료까지 시간이 걸려요 — 잠시 후 생성 결과를 물어보면 확인해 드릴게요.",
                "meta": {"source": "generator", "label": "생성 실행", "engine": "파이프라인"},
            }
        res = await gen(
            AssistantRequest(question=state["question"], context_id=state.get("context_id"))
        )
        return {"answer": res.answer, "meta": _assistant_meta(res, "generator", "생성 어시스턴트")}

    async def advise_node(state) -> dict:
        resp = await llm.ainvoke(
            [SystemMessage(content=_ADVISE_SYSTEM), HumanMessage(content=state["question"])]
        )
        ans = resp.content if isinstance(resp.content, str) else ""
        return {
            "answer": ans,
            "meta": {"source": "orchestrator", "label": "CLIO", "engine": f"OpenAI · {model_name}"},
        }

    def route(state) -> str:
        return state.get("intent", "advise")

    g = StateGraph(_State)
    g.add_node("classify", classify)
    g.add_node("management", management_node)
    g.add_node("simulation", simulation_node)
    g.add_node("generator", generator_node)
    g.add_node("advise", advise_node)
    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        route,
        {
            "management": "management",
            "simulation": "simulation",
            "generator": "generator",
            "advise": "advise",
        },
    )
    for _node in ("management", "simulation", "generator", "advise"):
        g.add_edge(_node, END)
    graph = g.compile()

    async def _ask_full(turn: ChatTurn) -> ChatAnswer:
        # 1턴 = 1 트레이스 루트(classify → route → 서브에이전트).
        final = await graph.ainvoke(
            {"question": turn.question},
            config={
                "run_name": "assistant_chat",
                "tags": ["chat", "orchestrator"],
                "metadata": {"ad_id": turn.ad_id},
            },
        )
        meta = final.get("meta") or {
            "source": "orchestrator",
            "label": "CLIO",
            "engine": f"OpenAI · {model_name}",
        }
        return ChatAnswer(answer=final.get("answer", ""), meta=meta)

    return _ask_full
