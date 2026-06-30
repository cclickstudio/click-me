# 공통 오케스트레이터 Deep Agent — LangGraph 3노드 루프 (act-first, MAX_ITER=3)
"""단일 패스 Orchestrator를 대체하는 Deep Agent.

act-first 전략: 첫 이터레이션에 management 질문이면 즉시 호출하고, 결과 보고 최종 답 합성.
루프 상한(MAX_ITER=3)으로 비용 통제. requires_approval=True면 즉시 합성(재호출 없음).

반환 인터페이스: SubagentResult (기존 Orchestrator 계약과 동일).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from api.assistant.contracts import Action, SubagentRequest, SubagentResult
from api.assistant.registry import Handler
from core.schemas import ChatMessage

logger = logging.getLogger("clickme")

MAX_ITER = 3

_SYS_ORCHESTRATOR = """\
당신은 ClickMe 광고 플랫폼의 오케스트레이터 AI입니다.
도구(ask_management, ask_simulation, ask_generator)를 호출해 정보를 수집한 뒤,
한국어로 최종 답변을 작성합니다.

규칙:
- 광고 운영·성과·예산·정책 질문 → ask_management 호출
- 집행 전 시뮬 결과·KPI(클릭의향률·구매의도·신뢰도·거부율) 해석 → ask_simulation 호출
- 광고 시안·카피 생성 요청 → ask_generator 호출
- 새 캠페인 생성 요청("캠페인 만들어줘" 등) → create_campaign 호출(발화의 값을 인자로)
- 기존 캠페인 일시중지·게재 시작·예산 증액/감액 요청 → manage_campaign 호출
- 새 시뮬레이션 실행 요청("이 광고 시뮬 돌려줘" 등) → run_simulation 호출(발화의 값을 인자로)
- 이미 충분한 정보가 있으면 추가 호출 없이 답합니다
- 최종 답변에 수치·근거가 있으면 도구 결과에서 그대로 인용합니다
"""

# 도구 스펙 정의 (LLM function-calling)
_TOOL_SPECS = [
    {
        "name": "ask_management",
        "description": (
            "캠페인 현황·성과·예산·이상·KPI·벤치마크·정책 관련 질문."
            " 실측 데이터와 KB 정책 근거를 제공한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "질문 내용"},
                "campaign_id": {
                    "type": "string",
                    "description": "특정 캠페인 ID (선택)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_simulation",
        "description": (
            "집행 '전' 시뮬레이션 결과·예측·KPI(클릭 의향률·구매의도·신뢰도·거부율)의"
            " 의미·해석 질문. 이미 돌린 시뮬 결과를 조회·해석해 근거와 함께 답한다."
            " (새 시뮬을 돌리는 게 아니라 기존 결과 조회·해석. 실행은 run_simulation.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "질문 내용"},
                "simulation_id": {
                    "type": "string",
                    "description": "특정 시뮬레이션 ID (선택)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_generator",
        "description": (
            "광고 시안·카피·이미지 생성 요청."
            " management_context로 성과 기반 개선 컨텍스트를 전달할 수 있다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "생성 요청 내용"},
                "management_context": {
                    "type": "string",
                    "description": "매니지먼트 결과(성과·제약 맥락) (선택)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_campaign",
        "description": (
            "사용자가 '새 광고 캠페인을 만들어 달라'고 요청할 때 호출한다."
            " 캠페인 생성 폼 카드를 띄운다. 발화에 값이 있으면 인자로 채우고, 없으면 생략한다."
            " (생성 방법 질문·성과 분석엔 호출하지 않는다.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "캠페인 이름(언급 시)"},
                "objective": {
                    "type": "string",
                    "enum": ["traffic", "leads"],
                    "description": "traffic=클릭, leads=잠재고객·전환",
                },
                "total_budget_krw": {
                    "type": "integer",
                    "description": "총 예산 원 단위 정수(언급 시, '5만원'=50000)",
                },
            },
        },
    },
    {
        "name": "manage_campaign",
        "description": (
            "기존 캠페인 상태·예산 변경 요청에 호출한다. action='pause'|'activate'|"
            "'increase_budget'|'decrease_budget'."
            " 예산 변경이면 new_daily_budget_krw 또는 pct를 채운다."
            " 특정 가능하면 campaign_id, 모르면 비운다. 생성엔 호출하지 않는다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pause", "activate", "increase_budget", "decrease_budget"],
                },
                "campaign_id": {"type": "string", "description": "대상 캠페인 ID(알면)"},
                "campaign_name": {
                    "type": "string",
                    "description": "사용자가 말한 캠페인 이름(있으면)",
                },
                "new_daily_budget_krw": {
                    "type": "integer",
                    "description": "예산 변경 시 목표 일예산 원(언급 시, '5만원'=50000)",
                },
                "pct": {
                    "type": "integer",
                    "description": "예산 변경 비율 %(언급 시, '25% 올려'=25, 내림은 음수)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "run_simulation",
        "description": (
            "사용자가 '이 광고로 시뮬레이션을 돌려 달라'고 요청할 때 호출한다."
            " 시뮬 입력 폼 카드를 띄운다. 발화에 값이 있으면 인자로 채우고, 없으면 생략한다."
            " (KPI 의미·기존 결과 해석 질문엔 호출하지 않는다 — 그건 ask_simulation.)"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ad_title": {"type": "string", "description": "광고 제목(언급 시)"},
                "ad_content": {"type": "string", "description": "광고 카피·문구(언급 시)"},
                "product_category": {
                    "type": "string",
                    "description": "제품 카테고리(언급 시)",
                },
                "ad_objective": {"type": "string", "description": "광고 목표(언급 시)"},
            },
        },
    },
]

# ── Memory(딥에이전트 ③기둥) — 에이전트가 도구로 장기기억을 직접 읽고 쓴다 ──────
_MEMORY_TOOL_SPECS = [
    {
        "name": "remember",
        "description": (
            "다음 대화에서도 기억할 가치가 있는 사용자 선호·결정·반복 관심을 장기기억에 저장한다."
            " 일회성 정보·인사·잡담은 저장하지 않는다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "한 줄 사실(선호·결정 등)"},
                "kind": {
                    "type": "string",
                    "enum": ["semantic", "episodic", "profile"],
                    "description": "semantic(사실·선호) | episodic(사건) | profile(지속 프로필)",
                },
            },
            "required": ["fact"],
        },
    },
    {
        "name": "recall",
        "description": "과거 세션에서 저장한 사용자 장기기억을 의미 기반으로 조회한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "조회할 맥락·주제"},
            },
            "required": ["query"],
        },
    },
]

# ── Planning(딥에이전트 ①기둥) — 요청을 명시적 할일로 분해 ─────────────────────
_SYS_PLANNER = """\
당신은 ClickMe 광고 플랫폼 오케스트레이터의 플래너입니다.
사용자 요청을 실행 가능한 할일(todo)로 분해합니다.
가용 능력: ask_management(운영·성과·예산·이상·정책), ask_simulation(집행 전 시뮬 결과·KPI 해석),
ask_generator(시안·카피 생성), 직접 답변.

규칙:
- 여러 능력이 필요하거나 순서가 있는 다단계 요청만 2~5개 단계로 쪼갠다.
- 단순·단일 질문, 인사, 되묻기, 잡담은 빈 리스트([])를 반환한다(계획 불필요).
- 각 단계는 한국어 동사구 한 줄(예: "운영 캠페인 실측 조회").
"""


class _Plan(BaseModel):
    """플래너 구조화 출력 — 다단계면 단계 목록, 단순 요청이면 빈 리스트."""

    steps: list[str] = Field(default_factory=list)


_STATUS_MARK = {"pending": "⬜", "in_progress": "⏳", "completed": "✅"}


def _render_plan(plan: list[dict]) -> str:
    """계획을 오케스트레이터 컨텍스트·프론트 표시용 텍스트로."""
    return "\n".join(
        f"{_STATUS_MARK.get(p['status'], '⬜')} {i + 1}. {p['step']}" for i, p in enumerate(plan)
    )


def _advance_plan(plan: list[dict]) -> list[dict]:
    """한 dispatch 라운드 = 한 단계 진행. in_progress→completed, 다음 pending→in_progress."""
    out = [dict(p) for p in plan]
    advanced = False
    for p in out:
        if p["status"] == "in_progress":
            p["status"] = "completed"
            advanced = True
            break
    if advanced:
        for p in out:
            if p["status"] == "pending":
                p["status"] = "in_progress"
                break
    return out


class _OState(TypedDict):
    """오케스트레이터 내부 상태."""

    messages: Annotated[list, add_messages]
    orig_messages: list  # 핸들러에 전달할 원본 ChatMessage (변경 안 됨)
    sub_results: dict[str, Any]
    iteration: int
    thread_id: str | None
    requires_approval: bool
    session_id: str
    context_ad_id: str | None
    memory_context: str | None  # 장기기억(M1) — 서브에이전트 req로 전달
    plan: list[dict]  # Planning — todo 리스트 [{step, status}], 단순 요청은 []
    iter_budget: int  # 동적 루프 상한(계획 길이에 맞춰 plan 노드가 설정)
    user_id: str | None  # Memory 스코프 — remember/recall 도구가 사용
    tenant_id: str | None
    create_prefill: dict | None  # create_campaign 툴이 채운 폼 초기값(없으면 None)
    campaign_action: dict | None  # manage_campaign 툴 페이로드(action·campaign_id·campaign_name)
    sim_form: dict | None  # run_simulation 툴이 채운 시뮬 입력 폼 초기값(없으면 None)


def _chat_to_lc(m: ChatMessage) -> HumanMessage | AIMessage:
    """ChatMessage → LangChain message 객체."""
    if m.role == "user":
        return HumanMessage(content=m.content)
    return AIMessage(content=m.content)


def _sub_to_text(result: SubagentResult) -> str:
    """SubagentResult → 도구 응답 텍스트 (LLM이 읽을 수 있도록 직렬화)."""
    meta = result.meta or {}
    lines = [result.message]
    if meta.get("citations"):
        refs = "; ".join(
            f"{c.get('title', '?')}({c.get('source', '?')})" for c in meta["citations"][:3]
        )
        lines.append(f"[인용: {refs}]")
    if meta.get("requires_approval"):
        lines.append("[HITL: 사람 승인 필요]")
    return "\n".join(lines)


def build_deep_agent_graph(
    llm,
    management_handler: Handler | None = None,
    generator_handler: Handler | None = None,
    simulation_handler: Handler | None = None,
    checkpointer=None,
    memory=None,
) -> Callable[[SubagentRequest], Awaitable[SubagentResult]]:
    """Deep Agent 팩토리 — graph를 빌드하고 run(SubagentRequest) → SubagentResult를 반환.

    management_handler / generator_handler / simulation_handler가 None이면 mock 핸들러로 대체.
    실 구현이 들어오면 wiring.py에서 실 핸들러를 주입해 교체.
    checkpointer가 None이면 MemorySaver(인메모리). wiring이 PG 싱글턴을 주입하면 영속·멀티턴.
    memory(ManagementMemory) 주입 시 remember/recall 도구를 노출(딥에이전트 Memory 기둥).
    """
    _mgt_handler = management_handler or _mock_management
    _gen_handler = generator_handler or _mock_generator
    _sim_handler = simulation_handler or _mock_simulation

    # ── LLM 준비 (function calling 바인딩) ──────────────────────────────────
    # memory 주입 시에만 remember/recall 도구를 노출(미주입 배포엔 유령 도구 안 생김).
    tool_specs = [*_TOOL_SPECS, *(_MEMORY_TOOL_SPECS if memory else [])]
    llm_with_tools = llm.bind_tools(tool_specs)
    llm_plain = llm  # MAX_ITER 도달 시 도구 없이 최종 답 생성

    # ── 노드 정의 ────────────────────────────────────────────────────────────

    async def plan_node(state: _OState) -> dict:
        """Planning — 요청을 명시적 할일로 분해(다단계만). 단순 요청은 빈 계획."""
        try:
            structured = llm.with_structured_output(_Plan)
            result: _Plan = await structured.ainvoke(
                [SystemMessage(content=_SYS_PLANNER), *state["messages"]],
                config={"run_name": "deep-agent.plan", "tags": ["deep-agent", "planning"]},
            )
            steps = [s.strip() for s in result.steps if s.strip()][:5]
        except Exception:  # noqa: BLE001 — 계획 실패는 빈 계획으로 진행(기존 동작과 동일)
            steps = []
        plan = [{"step": s, "status": "pending"} for s in steps]
        if plan:
            plan[0]["status"] = "in_progress"  # 첫 단계 착수
        # 다단계면 계획 길이에 맞춰 루프 예산 확장(얕은 MAX_ITER로 안 잘리게)
        return {"plan": plan, "iter_budget": max(MAX_ITER, len(plan) + 1)}

    def _orchestrator_sys(state: _OState, extra: str = "") -> SystemMessage:
        """오케스트레이터 시스템 메시지 — 현재 계획·상태를 함께 주입(plan→act→observe)."""
        content = _SYS_ORCHESTRATOR
        plan = state.get("plan") or []
        if plan:
            content += (
                f"\n\n현재 계획:\n{_render_plan(plan)}\n"
                "다음 미완료(⏳/⬜) 단계를 진행하라. 모든 단계가 끝났으면 최종 답변을 작성하라."
            )
        return SystemMessage(content=content + extra)

    async def orchestrate(state: _OState) -> dict:
        """LLM이 도구 호출 여부를 결정하는 노드(현재 계획을 컨텍스트로 본다)."""
        # 카드 신호(create_campaign/manage_campaign 툴)가 세팅되면 추가 LLM 합성·루프 없이
        # 고정 안내로 즉시 종료(신호 툴은 sub-agent 아님 — 더 돌면 무의미한 재합성/무한루프).
        if state.get("create_prefill") is not None:
            return {
                "messages": [
                    AIMessage(
                        content="새 캠페인 생성 폼을 준비했어요. 값을 확인하고 승인해 주세요."
                    )
                ],
                "iteration": state["iteration"] + 1,
            }
        if state.get("campaign_action") is not None:
            return {
                "messages": [
                    AIMessage(
                        content="요청하신 캠페인 조치를 확인 카드로 준비했어요. 확인해 주세요."
                    )
                ],
                "iteration": state["iteration"] + 1,
            }
        if state.get("sim_form") is not None:
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "시뮬레이션 입력 폼을 준비했어요. 광고 정보를 확인하고 실행해 주세요."
                        )
                    )
                ],
                "iteration": state["iteration"] + 1,
            }
        budget = state.get("iter_budget") or MAX_ITER
        if state["iteration"] >= budget or state["requires_approval"]:
            # 더 이상 도구 호출 없이 최종 합성
            resp = await llm_plain.ainvoke(state["messages"])
            return {"messages": [resp], "iteration": state["iteration"] + 1}

        # act-first: 첫 이터레이션에서 도구 선택을 유도 + 계획 주입
        messages = list(state["messages"])
        if state["iteration"] == 0 and not state["sub_results"]:
            messages = [
                _orchestrator_sys(state, "\n첫 응답에서 적합한 도구를 즉시 호출하세요."),
                *messages,
            ]
        elif state.get("plan"):
            messages = [_orchestrator_sys(state), *messages]

        resp = await llm_with_tools.ainvoke(messages)
        return {"messages": [resp], "iteration": state["iteration"] + 1}

    async def dispatch(state: _OState) -> dict:
        """tool_calls를 실행해 sub_results에 저장하고 ToolMessage를 반환하는 노드."""
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", [])

        tool_msgs: list[ToolMessage] = []
        new_sub = dict(state["sub_results"])
        new_thread_id = state["thread_id"]
        new_requires = state["requires_approval"]

        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args", {})
            tool_id = tc.get("id", name)

            try:
                if name == "ask_management":
                    req = SubagentRequest(
                        messages=state["orig_messages"],
                        session_id=state["session_id"],
                        context_ad_id=args.get("campaign_id") or state["context_ad_id"],
                        memory_context=state.get("memory_context"),  # M1 — 장기기억 주입
                    )
                    result: SubagentResult = await _mgt_handler(req)
                    new_sub["management"] = result.meta
                    if result.meta.get("thread_id"):
                        new_thread_id = result.meta["thread_id"]
                    if result.meta.get("requires_approval"):
                        new_requires = True

                elif name == "ask_simulation":
                    # 집행 전 시뮬 결과·KPI 조회·해석(조언형). 실행은 run_simulation 신호 도구.
                    req = SubagentRequest(
                        messages=state["orig_messages"],
                        session_id=state["session_id"],
                        context_ad_id=args.get("simulation_id") or state["context_ad_id"],
                    )
                    result = await _sim_handler(req)
                    new_sub["simulation"] = result.meta

                elif name == "ask_generator":
                    mgt_ctx = args.get("management_context") or (
                        new_sub.get("management", {}).get("summary", "")
                    )
                    req = SubagentRequest(
                        messages=state["orig_messages"],
                        session_id=state["session_id"],
                    )
                    if mgt_ctx:
                        req.improve_context = {"summary": mgt_ctx}
                    result = await _gen_handler(req)
                    new_sub["generator"] = result.meta
                    # ASK/TRIGGER → 즉시 END (되묻기/트리거는 루프 없이 전달)
                    if result.action in (Action.ASK, Action.TRIGGER):
                        tool_msgs.append(
                            ToolMessage(
                                content=_sub_to_text(result),
                                tool_call_id=tool_id,
                            )
                        )
                        return {
                            "messages": tool_msgs,
                            "sub_results": new_sub,
                            "thread_id": new_thread_id,
                            "requires_approval": new_requires,
                        }

                elif name == "remember":
                    # Memory 기둥 — 에이전트가 장기기억에 직접 저장. dedup_key=fact 해시(upsert).
                    fact = (args.get("fact") or "").strip()
                    if memory and state.get("user_id") and fact:
                        kind = args.get("kind") or "semantic"
                        key = f"{kind}:{hashlib.sha1(fact.encode()).hexdigest()[:16]}"
                        await memory.remember(
                            state.get("tenant_id"),
                            state["user_id"],
                            key,
                            {"kind": kind, "fact": fact},
                        )
                        tool_msgs.append(ToolMessage(content="기억했습니다.", tool_call_id=tool_id))
                    else:
                        tool_msgs.append(
                            ToolMessage(
                                content="저장 생략(내용 없음/비로그인).", tool_call_id=tool_id
                            )
                        )
                    continue

                elif name == "recall":
                    facts: list[str] = []
                    if memory and state.get("user_id"):
                        rows = await memory.recall(
                            state.get("tenant_id"),
                            state["user_id"],
                            query=args.get("query"),
                            limit=5,
                        )
                        facts = [r.get("fact") for r in rows if r.get("fact")]
                    tool_msgs.append(
                        ToolMessage(
                            content="\n".join(f"- {f}" for f in facts) or "(저장된 기억 없음)",
                            tool_call_id=tool_id,
                        )
                    )
                    continue

                elif name == "create_campaign":
                    # 폼 prefill만 추출(빈 값 제거). DB 미접촉 — 카드를 띄우는 신호일 뿐.
                    prefill = {
                        k: v
                        for k, v in args.items()
                        if k in ("name", "objective", "total_budget_krw") and v
                    }
                    if prefill.get("objective") not in ("traffic", "leads"):
                        prefill.pop("objective", None)  # enum 밖 값은 폼 기본값에 맡긴다
                    tool_msgs.append(
                        ToolMessage(content="생성 폼을 준비했습니다.", tool_call_id=tool_id)
                    )
                    return {
                        "messages": tool_msgs,
                        "sub_results": new_sub,
                        "thread_id": new_thread_id,
                        "requires_approval": new_requires,
                        "create_prefill": prefill,
                    }

                elif name == "manage_campaign":
                    action_payload = {
                        k: v
                        for k, v in args.items()
                        if k
                        in (
                            "action",
                            "campaign_id",
                            "campaign_name",
                            "new_daily_budget_krw",
                            "pct",
                        )
                        and v is not None
                    }
                    valid_actions = ("pause", "activate", "increase_budget", "decrease_budget")
                    if action_payload.get("action") not in valid_actions:
                        # 파싱 깨졌을 때 pause로 떨어뜨리지 않는다(안전 fallback 아님).
                        # 카드 미생성 → campaign_action 미설정, ToolMessage로 재질문을 유도한다.
                        tool_msgs.append(
                            ToolMessage(
                                content=(
                                    "어떤 조치인지 명확하지 않아요. "
                                    "무엇을(중지/게재/예산 변경) 어느 캠페인에 할지 "
                                    "다시 알려 주세요."
                                ),
                                tool_call_id=tool_id,
                            )
                        )
                        return {
                            "messages": tool_msgs,
                            "sub_results": new_sub,
                            "thread_id": new_thread_id,
                            "requires_approval": new_requires,
                        }
                    tool_msgs.append(
                        ToolMessage(content="조치 확인 카드를 준비했습니다.", tool_call_id=tool_id)
                    )
                    return {
                        "messages": tool_msgs,
                        "sub_results": new_sub,
                        "thread_id": new_thread_id,
                        "requires_approval": new_requires,
                        "campaign_action": action_payload,
                    }

                elif name == "run_simulation":
                    # 시뮬 입력값만 추출. DB 미접촉 — sim_form 카드를 띄우는 신호일 뿐.
                    # 실제 실행은 프론트가 기존 시뮬 라우터로(create_campaign과 동일 신호 패턴).
                    sim_data = {
                        "ad_title": args.get("ad_title") or None,
                        "ad_content": args.get("ad_content") or "",
                        "product_category": args.get("product_category") or None,
                        "ad_objective": args.get("ad_objective") or None,
                    }
                    tool_msgs.append(
                        ToolMessage(
                            content="시뮬레이션 입력 폼을 준비했습니다.", tool_call_id=tool_id
                        )
                    )
                    return {
                        "messages": tool_msgs,
                        "sub_results": new_sub,
                        "thread_id": new_thread_id,
                        "requires_approval": new_requires,
                        "sim_form": sim_data,
                    }

                else:
                    result = SubagentResult(
                        action=Action.ANSWER,
                        message=f"[알 수 없는 도구: {name}]",
                    )

                tool_msgs.append(ToolMessage(content=_sub_to_text(result), tool_call_id=tool_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[deep_agent] %s 실패: %s", name, exc)
                tool_msgs.append(ToolMessage(content=f"[{name} 오류: {exc}]", tool_call_id=tool_id))

        return {
            "messages": tool_msgs,
            "sub_results": new_sub,
            "thread_id": new_thread_id,
            "requires_approval": new_requires,
            # observe — 한 라운드 끝났으니 계획 한 단계 전진(있을 때만).
            "plan": _advance_plan(state["plan"]) if state.get("plan") else [],
        }

    def route(state: _OState) -> str:
        """tool_calls가 있으면 dispatch, 없으면 END."""
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "dispatch"
        return END

    # ── 그래프 빌드 ── plan(계획) → orchestrate(act) ⇄ dispatch(observe) ──────
    builder = StateGraph(_OState)
    builder.add_node("plan", plan_node)
    builder.add_node("orchestrate", orchestrate)
    builder.add_node("dispatch", dispatch)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "orchestrate")
    builder.add_conditional_edges("orchestrate", route, {"dispatch": "dispatch", END: END})
    builder.add_edge("dispatch", "orchestrate")

    # 외부 주입(PG 싱글턴) 우선, 없으면 인메모리 폴백(Windows 로컬·테스트).
    graph = builder.compile(checkpointer=checkpointer or MemorySaver())

    # ── 공개 인터페이스 ───────────────────────────────────────────────────────

    async def run(req: SubagentRequest) -> SubagentResult:
        """SubagentRequest → SubagentResult (기존 Orchestrator 계약 유지)."""
        lc_messages = [_chat_to_lc(m) for m in req.messages]

        initial: _OState = {
            "messages": lc_messages,
            "orig_messages": req.messages,
            "sub_results": {},
            "iteration": 0,
            "thread_id": None,
            "requires_approval": False,
            "session_id": req.session_id or "",
            "context_ad_id": req.context_ad_id,
            "memory_context": req.memory_context,
            "plan": [],
            "iter_budget": MAX_ITER,
            "user_id": req.user_id,
            "tenant_id": req.org_id,
            "create_prefill": None,
            "campaign_action": None,
            "sim_form": None,
        }

        config = {
            "run_name": "deep-agent-turn",
            "tags": ["deep-agent", "orchestrator", "management"],
            "metadata": {
                "session_id": req.session_id,
                "iteration_budget": MAX_ITER,
            },
            # M4 — 요청별 고유 thread_id. 프론트가 매 턴 풀히스토리를 재전송하므로 오케스트레이터는
            # 요청 단위로 독립(stateless)이어야 한다. session_id로 고정하면 체크포인터가 누적하고
            # add_messages가 ID 미부여로 dedup 못 해 메시지가 중복된다. HITL 재개는 management
            # 서브그래프(mgmt-{session_id} thread)가 담당하므로 오케스트레이터 thread는 일회용.
            "configurable": {"thread_id": f"orch-{req.session_id or 'anon'}-{uuid4().hex[:8]}"},
        }

        final: _OState = await graph.ainvoke(initial, config=config)
        return _state_to_result(final)

    return run


def _state_to_result(state: _OState) -> SubagentResult:
    """최종 state → SubagentResult 변환."""
    # 마지막 AI 메시지에서 최종 텍스트 추출
    final_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            final_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    # management sub_result에서 meta 재구성
    mgt_meta = state["sub_results"].get("management", {})
    sim_meta = state["sub_results"].get("simulation", {})
    gen_meta = state["sub_results"].get("generator", {})
    # 호출된 서브에이전트 중 주 소스를 source로 — frontend가 source로 분기하므로 유지
    primary_source = (
        mgt_meta.get("source", "management")
        if mgt_meta
        else sim_meta.get("source", "simulation")
        if sim_meta
        else gen_meta.get("source", "generator")
        if gen_meta
        else "deep-agent"
    )
    combined_meta: dict = {
        "source": primary_source,
        "label": mgt_meta.get(
            "label", sim_meta.get("label", gen_meta.get("label", "오케스트레이터"))
        ),
        "engine": mgt_meta.get(
            "engine", sim_meta.get("engine", gen_meta.get("engine", "Deep Agent"))
        ),
        "citations": (
            mgt_meta.get("citations", [])
            + sim_meta.get("citations", [])
            + gen_meta.get("citations", [])
        ),
        "used_tools": (
            mgt_meta.get("used_tools", [])
            + (["ask_management"] if mgt_meta else [])
            + (["ask_simulation"] if sim_meta else [])
            + (["ask_generator"] if gen_meta else [])
        ),
        "requires_approval": state["requires_approval"],
        "thread_id": state["thread_id"],
        # Planning(딥에이전트 ①기둥) — 프론트 체크리스트 위젯용. 최종 답이 나왔으면 전부 완료 처리.
        "plan": [
            {**p, "status": "completed" if not state["requires_approval"] else p["status"]}
            for p in (state.get("plan") or [])
        ],
        # G2 — suggested_action/evidence/campaigns 캐리. 누락 시 RESULT/REVIEW/ACTIONBAR
        # 카드가 영영 안 뜨고(chat.py compose_turn 입력 부재), record_turn·메모리 노트도 빈값.
        "suggested_action": mgt_meta.get("suggested_action"),
        "evidence": mgt_meta.get("evidence", {}),
        "campaigns": mgt_meta.get("campaigns", []),
        "sub_results": {
            "management": _compact_meta(mgt_meta),
            "simulation": _compact_meta(sim_meta),
            "generator": _compact_meta(gen_meta),
        },
    }

    # 챗→매니지먼트 카드 신호(재이식) — 3k 프론트의 meta.widget 통로로 흘려보낸다(W0).
    # 프론트 ChatConversation이 widget.type으로 분기해 카드를 렌더한다.
    if state.get("create_prefill") is not None:
        combined_meta["widget"] = {
            "type": "create_campaign",
            "data": {"prefill": state["create_prefill"]},
        }
        # create 신호가 권위 — 멀티툴 턴에서도 source를 deep-agent로 고정해
        # chat.py의 management 게이트(카드 빌드·record_turn) 오발동을 막는다.
        combined_meta["source"] = "deep-agent"
    if state.get("campaign_action") is not None:
        combined_meta["widget"] = {
            "type": "campaign_action",
            "data": {"action": state["campaign_action"]},
        }
        combined_meta["source"] = "deep-agent"
    # 시뮬 실행 신호(run_simulation) — 기존 sim_form 위젯 통로로 흘려보낸다.
    # source는 "simulation" 고정 — 기존 simulation_node와 동일 조합이라
    # 프론트·chat.py가 그대로 처리한다.
    if state.get("sim_form") is not None:
        combined_meta["widget"] = {
            "type": "sim_form",
            "data": state["sim_form"],
        }
        combined_meta["source"] = "simulation"

    return SubagentResult(
        action=Action.ANSWER,
        message=final_text,
        meta=combined_meta,
    )


def _compact_meta(meta: dict) -> dict | None:
    if not meta:
        return None
    return {k: v for k, v in meta.items() if k in ("source", "label", "engine", "citations")}


# ── Mock 핸들러 (실 구현 전까지 wiring.py에서 주입) ───────────────────────────


async def _mock_management(req: SubagentRequest) -> SubagentResult:
    """management 실 구현 전 mock — wiring.py에서 실 핸들러로 교체."""
    return SubagentResult(
        action=Action.ANSWER,
        message=f"[MOCK-MGT] 매니지먼트 응답 (query={req.last_user_text[:40]}...)",
        meta={"source": "management", "citations": [], "used_tools": ["mock"]},
    )


async def _mock_generator(req: SubagentRequest) -> SubagentResult:
    """generator 실 구현 전 mock — wiring.py에서 실 핸들러로 교체."""
    return SubagentResult(
        action=Action.ANSWER,
        message=f"[MOCK-GEN] 광고 시안 생성 완료 (query={req.last_user_text[:40]}...)",
        meta={"source": "generator", "citations": [], "used_tools": ["mock"]},
    )


async def _mock_simulation(req: SubagentRequest) -> SubagentResult:
    """simulation 실 구현 전 mock — wiring.py에서 실 핸들러로 교체."""
    return SubagentResult(
        action=Action.ANSWER,
        message=f"[MOCK-SIM] 시뮬레이션 응답 (query={req.last_user_text[:40]}...)",
        meta={"source": "simulation", "citations": [], "used_tools": ["mock"]},
    )


# ── 공개 심볼 ────────────────────────────────────────────────────────────────
__all__ = [
    "build_deep_agent_graph",
    "MAX_ITER",
    "_mock_management",
    "_mock_generator",
    "_mock_simulation",
]
