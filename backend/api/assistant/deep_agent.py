# 최상위 오케스트레이터 CLIO(Deep Agent) — deepagents create_deep_agent 기반 도구 루프
"""ClickMe 챗의 최상위 어드바이저 CLIO. 단일 패스 Orchestrator를 대체하는 Deep Agent.

CLIO는 도메인 서브에이전트를 도구로 부르고, 도구가 필요 없는 일반 광고/마케팅 질문엔 직접 답한다.

서브에이전트(ask_management/ask_simulation/ask_generator)와 신호 도구(create_campaign/
manage_campaign/run_simulation), 장기기억 도구(remember/recall)를 LangChain 도구로 등록하고
deepagents의 도구 루프·계획(todos)·파일 스크래치를 그대로 활용한다.

도구는 LLM에 텍스트를 돌려주되, 구조화 메타(citations·suggested_action·widget 신호)는
요청 스코프 contextvar 누산기에 적재한다. run() 종료 후 누산기 + 최종 메시지를 _state_to_result로
합성해 기존 Orchestrator 계약(SubagentResult)을 그대로 유지한다.
"""

from __future__ import annotations

import contextvars
import hashlib
import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage

from api.assistant.contracts import Action, SubagentRequest, SubagentResult
from api.assistant.registry import Handler

logger = logging.getLogger("clickme")

# 호환 유지 심볼(테스트·외부 참조). 도구 루프 재귀 상한 산정 기준으로도 쓴다.
MAX_ITER = 3
_RECURSION_LIMIT = 25

_SYS_ORCHESTRATOR = """\
당신은 ClickMe의 수석 광고 전략 AI 어드바이저 CLIO입니다.
도구(ask_management, ask_simulation, ask_generator)로 정보를 수집해 한국어로 답하되,
도구가 필요 없는 일반 광고·마케팅 전략·아이디어 질문이나 잡담에는 직접 간결히 답합니다.
문장 끝에 콜론을 쓰지 않습니다.

규칙:
- 광고 운영·성과·예산·정책 질문 → ask_management 호출
- 집행 전 시뮬 결과·KPI(클릭의향률·구매의도·신뢰도·거부율) 해석 → ask_simulation 호출
- 광고 시안·카피 '작성 원칙·전략' 질문 → ask_generator 호출
- 시안·카피를 실제로 '만들어 달라'는 요청("시안 만들어줘") → run_generator 호출(발화 값을 인자로)
- 새 캠페인 생성 요청("캠페인 만들어줘" 등) → create_campaign 호출(발화의 값을 인자로)
- 기존 캠페인 일시중지·게재 시작·예산 증액/감액 요청 → manage_campaign 호출
- 새 시뮬레이션 실행 요청("이 광고 시뮬 돌려줘" 등) → run_simulation 호출(발화의 값을 인자로)
- 위 도구 어디에도 안 맞는 일반 광고/마케팅 질문은 도구 없이 CLIO로서 직접 답합니다
- 이미 충분한 정보가 있으면 추가 호출 없이 답합니다
- 최종 답변에 수치·근거가 있으면 도구 결과에서 그대로 인용합니다
- 신호 도구(create_campaign/manage_campaign/run_simulation/run_generator)를 호출했으면,
  추가 도구 호출 없이 한 문장으로 마무리합니다(폼·확인 카드는 이미 준비됨)
"""

# 요청 스코프 컨텍스트 — 매 run마다 {"req", "acc"}를 주입(asyncio 태스크 안전).
_run_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar("deep_run_ctx", default=None)


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
    clio_kb_search: Callable[[str], Awaitable[list[dict]]] | None = None,
) -> Callable[[SubagentRequest], Awaitable[SubagentResult]]:
    """CLIO(Deep Agent) 팩토리 — deepagents 그래프를 빌드하고 run(SubagentRequest) → SubagentResult.

    management_handler / generator_handler / simulation_handler가 None이면 mock 핸들러로 대체.
    실 구현이 들어오면 wiring.py에서 실 핸들러를 주입해 교체.
    checkpointer가 None이면 비영속(요청별 고유 thread). memory(ManagementMemory) 주입 시
    remember/recall 도구를 노출(딥에이전트 Memory 기둥).
    clio_kb_search(query)→rows 주입 시 search_clio_kb 도구를 노출(CLIO 일반지식 인용).
    """
    from langchain_core.tools import tool  # noqa: PLC0415

    _mgt_handler = management_handler or _mock_management
    _gen_handler = generator_handler or _mock_generator
    _sim_handler = simulation_handler or _mock_simulation

    def _ctx() -> tuple[SubagentRequest, dict]:
        ctx = _run_ctx.get()
        if ctx is None:  # run() 밖에서 도구가 불릴 일은 없음(방어).
            raise RuntimeError("deep agent tool invoked outside run() context")
        return ctx["req"], ctx["acc"]

    @tool
    async def ask_management(query: str, campaign_id: str | None = None) -> str:
        """캠페인 현황·성과·예산·이상·KPI·벤치마크·정책 관련 질문.

        실측 데이터와 KB 정책 근거를 제공한다.
        """
        req, acc = _ctx()
        sub = SubagentRequest(
            messages=req.messages,
            session_id=req.session_id,
            context_ad_id=campaign_id or req.context_ad_id,
            memory_context=req.memory_context,  # M1 — 장기기억 주입
        )
        result = await _mgt_handler(sub)
        acc["sub_results"]["management"] = result.meta
        if result.meta.get("thread_id"):
            acc["thread_id"] = result.meta["thread_id"]
        if result.meta.get("requires_approval"):
            acc["requires_approval"] = True
        return _sub_to_text(result)

    @tool
    async def ask_simulation(query: str, simulation_id: str | None = None) -> str:
        """집행 '전' 시뮬레이션 결과·예측·KPI(클릭 의향률·구매의도·신뢰도·거부율)의 의미·해석 질문.

        이미 돌린 시뮬 결과를 조회·해석해 근거와 함께 답한다(새 시뮬 실행은 run_simulation).
        """
        req, acc = _ctx()
        sub = SubagentRequest(
            messages=req.messages,
            session_id=req.session_id,
            context_ad_id=simulation_id or req.context_ad_id,
        )
        result = await _sim_handler(sub)
        acc["sub_results"]["simulation"] = result.meta
        return _sub_to_text(result)

    @tool
    async def ask_generator(query: str, management_context: str | None = None) -> str:
        """광고 시안·카피·이미지 생성 요청.

        management_context로 성과 기반 개선 컨텍스트를 전달할 수 있다.
        """
        req, acc = _ctx()
        mgt_ctx = management_context or (
            acc["sub_results"].get("management", {}).get("summary", "")
        )
        sub = SubagentRequest(messages=req.messages, session_id=req.session_id)
        if mgt_ctx:
            sub.improve_context = {"summary": mgt_ctx}
        result = await _gen_handler(sub)
        acc["sub_results"]["generator"] = result.meta
        return _sub_to_text(result)

    @tool
    def create_campaign(
        name: str | None = None,
        objective: str | None = None,
        total_budget_krw: int | None = None,
    ) -> str:
        """사용자가 '새 광고 캠페인을 만들어 달라'고 요청할 때 호출한다.

        캠페인 생성 폼 카드를 띄운다. 발화에 값이 있으면 인자로 채우고, 없으면 생략한다.
        (생성 방법 질문·성과 분석엔 호출하지 않는다.) objective는 traffic=클릭, leads=잠재고객·전환.
        """
        _, acc = _ctx()
        prefill: dict = {}
        if name:
            prefill["name"] = name
        if objective in ("traffic", "leads"):  # enum 밖 값은 폼 기본값에 맡긴다
            prefill["objective"] = objective
        if total_budget_krw:
            prefill["total_budget_krw"] = total_budget_krw
        acc["create_prefill"] = prefill
        return "생성 폼을 준비했습니다."

    @tool
    def manage_campaign(
        action: str,
        campaign_id: str | None = None,
        campaign_name: str | None = None,
        new_daily_budget_krw: int | None = None,
        pct: int | None = None,
    ) -> str:
        """기존 캠페인 상태·예산 변경 요청에 호출한다.

        action='pause'|'activate'|'increase_budget'|'decrease_budget'. 예산 변경이면
        new_daily_budget_krw 또는 pct를 채운다('25% 올려'=25, 내림은 음수). 특정 가능하면
        campaign_id, 모르면 비운다. 생성엔 호출하지 않는다.
        """
        _, acc = _ctx()
        valid_actions = ("pause", "activate", "increase_budget", "decrease_budget")
        if action not in valid_actions:
            # 파싱 깨졌을 때 pause로 떨어뜨리지 않는다(안전 fallback 아님) — 재질문 유도.
            return (
                "어떤 조치인지 명확하지 않아요. "
                "무엇을(중지/게재/예산 변경) 어느 캠페인에 할지 다시 알려 주세요."
            )
        payload: dict = {"action": action}
        if campaign_id:
            payload["campaign_id"] = campaign_id
        if campaign_name:
            payload["campaign_name"] = campaign_name
        if new_daily_budget_krw is not None:
            payload["new_daily_budget_krw"] = new_daily_budget_krw
        if pct is not None:
            payload["pct"] = pct
        acc["campaign_action"] = payload
        return "조치 확인 카드를 준비했습니다."

    @tool
    def run_simulation(
        ad_title: str | None = None,
        ad_content: str | None = None,
        product_category: str | None = None,
        ad_objective: str | None = None,
    ) -> str:
        """사용자가 '이 광고로 시뮬레이션을 돌려 달라'고 요청할 때 호출한다.

        시뮬 입력 폼 카드를 띄운다. 발화에 값이 있으면 인자로 채우고, 없으면 생략한다.
        (KPI 의미·기존 결과 해석 질문엔 호출하지 않는다 — 그건 ask_simulation.)
        """
        _, acc = _ctx()
        acc["sim_form"] = {
            "ad_title": ad_title or None,
            "ad_content": ad_content or "",
            "product_category": product_category or None,
            "ad_objective": ad_objective or None,
        }
        return "시뮬레이션 입력 폼을 준비했습니다."

    @tool
    def run_generator(
        product_name: str | None = None,
        product_description: str | None = None,
        target_audience: str | None = None,
        campaign_objective: str | None = None,
    ) -> str:
        """사용자가 '광고 시안·카피를 만들어 달라'고 요청할 때 호출한다.

        생성 입력 폼 카드를 띄운다. 발화에 값이 있으면 인자로 채우고, 없으면 생략한다.
        (카피 전략·작성 원칙 '질문'엔 호출하지 않는다 — 그건 ask_generator.)
        """
        _, acc = _ctx()
        acc["gen_form"] = {
            "product_name": product_name or None,
            "product_description": product_description or None,
            "target_audience": target_audience or None,
            "campaign_objective": campaign_objective or "conversion",
        }
        return "생성 입력 폼을 준비했습니다."

    tools = [
        ask_management,
        ask_simulation,
        ask_generator,
        create_campaign,
        manage_campaign,
        run_simulation,
        run_generator,
    ]

    # Memory(딥에이전트 기둥) — memory 주입 시에만 노출(미주입 배포엔 유령 도구 안 생김).
    if memory:

        @tool
        async def remember(fact: str, kind: str = "semantic") -> str:
            """다음 대화에서도 기억할 가치가 있는 사용자 선호·결정·반복 관심을 장기기억에 저장한다.

            일회성 정보·인사·잡담은 저장하지 않는다.
            kind=semantic(사실·선호)|episodic(사건)|profile.
            """
            req, _ = _ctx()
            fact = (fact or "").strip()
            if req.user_id and fact:
                key = f"{kind}:{hashlib.sha1(fact.encode()).hexdigest()[:16]}"
                await memory.remember(req.org_id, req.user_id, key, {"kind": kind, "fact": fact})
                return "기억했습니다."
            return "저장 생략(내용 없음/비로그인)."

        @tool
        async def recall(query: str) -> str:
            """과거 세션에서 저장한 사용자 장기기억을 의미 기반으로 조회한다."""
            req, _ = _ctx()
            if req.user_id:
                rows = await memory.recall(req.org_id, req.user_id, query=query, limit=5)
                facts = [r.get("fact") for r in rows if r.get("fact")]
                return "\n".join(f"- {f}" for f in facts) or "(저장된 기억 없음)"
            return "(저장된 기억 없음)"

        tools += [remember, recall]

    # CLIO 일반지식 KB(RAG) — clio_kb_search 주입 시에만 노출. CLIO가 일반 광고/마케팅 질문에
    # 근거가 필요하면 호출해 인용 칩을 단다(시뮬·제너·매니지 도메인 KB와 분리).
    if clio_kb_search:

        @tool
        async def search_clio_kb(query: str) -> str:
            """일반 광고·마케팅 지식(용어·전략·정책)의 근거가 필요할 때 호출한다.

            도메인(시뮬·운영·생성)에 속하지 않는 일반지식 질문에만 쓰며, 결과를 인용해 답한다.
            """
            _, acc = _ctx()
            rows = await clio_kb_search(query)
            if not rows:
                return "(관련 일반지식 근거 없음)"
            for r in rows[:4]:
                acc["extra_citations"].append(
                    {
                        "kind": "kb",
                        "source": r.get("source"),
                        "title": r.get("title"),
                        "score": r.get("score"),
                    }
                )
            acc["extra_used_tools"].append("search_clio_kb")
            return "\n\n".join(f"[{r.get('title', '?')}] {r.get('chunk', '')}" for r in rows[:4])

        tools += [search_clio_kb]

    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=_SYS_ORCHESTRATOR,
        checkpointer=checkpointer,
    )

    async def run(req: SubagentRequest) -> SubagentResult:
        """SubagentRequest → SubagentResult (기존 Orchestrator 계약 유지)."""
        acc: dict = {
            "sub_results": {},
            "requires_approval": False,
            "thread_id": None,
            "create_prefill": None,
            "campaign_action": None,
            "sim_form": None,
            "gen_form": None,
            "plan": [],
            "extra_citations": [],
            "extra_used_tools": [],
        }
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        config = {
            "run_name": "deep-agent-turn",
            "tags": ["deep-agent", "orchestrator", "management"],
            "recursion_limit": _RECURSION_LIMIT,
            "metadata": {"session_id": req.session_id, "iteration_budget": MAX_ITER},
            # 요청별 고유 thread_id — 프론트가 매 턴 풀히스토리를 재전송하므로 오케스트레이터는
            # 요청 단위로 독립(stateless). HITL 재개는 management 서브그래프가 담당.
            "configurable": {"thread_id": f"orch-{req.session_id or 'anon'}-{uuid4().hex[:8]}"},
        }

        token = _run_ctx.set({"req": req, "acc": acc})
        try:
            out = await agent.ainvoke({"messages": messages}, config=config)
        finally:
            _run_ctx.reset(token)

        # 딥에이전트 계획(todos) → 프론트 plan 위젯 형식으로 매핑(사용했을 때만).
        acc["plan"] = [
            {"step": t.get("content", ""), "status": t.get("status", "completed")}
            for t in (out.get("todos") or [])
        ]
        state = {**acc, "messages": out["messages"]}
        return _state_to_result(state)

    return run


def _state_to_result(state: dict) -> SubagentResult:
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
        "label": mgt_meta.get("label", sim_meta.get("label", gen_meta.get("label", "CLIO"))),
        "engine": mgt_meta.get(
            "engine", sim_meta.get("engine", gen_meta.get("engine", "CLIO · Deep Agent"))
        ),
        "citations": (
            mgt_meta.get("citations", [])
            + sim_meta.get("citations", [])
            + gen_meta.get("citations", [])
            + state.get("extra_citations", [])  # CLIO 일반지식(search_clio_kb) 인용
        ),
        "used_tools": (
            mgt_meta.get("used_tools", [])
            + (["ask_management"] if mgt_meta else [])
            + (["ask_simulation"] if sim_meta else [])
            + (["ask_generator"] if gen_meta else [])
            + state.get("extra_used_tools", [])
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
    # 생성 실행 신호(run_generator) — 기존 gen_form 위젯 통로로 흘려보낸다(source="generator").
    if state.get("gen_form") is not None:
        combined_meta["widget"] = {
            "type": "gen_form",
            "data": state["gen_form"],
        }
        combined_meta["source"] = "generator"

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
