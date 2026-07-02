# 통합 채팅 에이전트 tool 모음 — LLM이 정책(prompts.py)에 따라 호출하는 액션·위임·메모리 도구
"""tool이 실행을 담당하고 판단은 LLM이 한다(정책=프롬프트).

위임 tool은 wiring.py의 도메인 핸들러(SubagentRequest→SubagentResult)를 재사용한다.
위젯 tool은 widgets.py 형태를 Command(update=...)로 상태에 적재 — 슬롯은 LLM이 인자로 추출한다.
per-turn 컨텍스트(session_id·project_id…)는 InjectedState로 읽는다(closure로 못 잡는 값).
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from api.assistant.contracts import SubagentRequest
from api.assistant.wiring import (
    _build_generator_handler,
    _build_management_handler,
    _build_simulation_handler,
)
from core.schemas import ChatMessage
from domain.chat import helpers, history, widgets
from domain.generator.assistant.tools import list_generations
from domain.simulation.assistant.tools import list_simulations

_VALID_CAMPAIGN_ACTIONS = ("pause", "activate", "increase_budget", "decrease_budget")


def _subreq(state: dict, query: str) -> SubagentRequest:
    """현재 상태 + LLM이 정리한 query로 SubagentRequest 구성(history는 user/assistant 텍스트만)."""
    history_msgs: list[ChatMessage] = []
    for m in state.get("messages", []) or []:
        cls = m.__class__.__name__
        content = getattr(m, "content", None)
        if not isinstance(content, str) or getattr(m, "tool_calls", None):
            continue
        if cls == "HumanMessage":
            history_msgs.append(ChatMessage(role="user", content=content))
        elif cls == "AIMessage":
            history_msgs.append(ChatMessage(role="assistant", content=content))
    history_msgs.append(ChatMessage(role="user", content=query))
    return SubagentRequest(
        messages=history_msgs,
        session_id=state.get("session_id") or "",
        user_id=state.get("user_id"),
        org_id=state.get("org_id"),
        project_id=state.get("project_id"),
        context_ad_id=state.get("context_ad_id"),
        memory_context=state.get("memory_context"),
    )


def build_chat_tools(settings, memory=None) -> list:
    """통합 채팅 에이전트에 등록할 tool 리스트를 빌드한다(settings·핸들러·메모리 클로저)."""
    mgmt = _build_management_handler(settings)
    gen = _build_generator_handler(settings)
    sim = _build_simulation_handler(settings)

    # ───────────────────────── 위임 tool (도메인 서브에이전트) ─────────────────────────
    @tool
    async def ask_management(
        query: str,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """집행 '후' 실측 성과·운영 질문, 그리고 캠페인 운영·성과 개선·예산 배분·타깃/오디언스
        전략에 관한 일반 조언에 답한다. 캠페인 예산·소진·CTR/ROAS/CVR 실적·페이싱·이상·정책·
        벤치마크 등. query에는 사용자의 질문을 명확히 정리해 넣어라."""
        res = await mgmt(_subreq(state, query))
        return Command(
            update={
                "sub_meta": {"management": res.meta},
                "messages": [ToolMessage(res.message, tool_call_id=tool_call_id)],
            }
        )

    @tool
    async def ask_simulation(
        query: str,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """집행 '전' 시뮬레이션 결과·KPI(클릭 의향률·구매의도·신뢰도·거부율)의 의미·해석·
        기존 결과 조회, 그리고 소비자 반응 예측에 관한 질문·조언에 답한다.
        (새 시뮬 실행이 아니라 해석·조회·조언. 실행은 run_simulation.)"""
        res = await sim(_subreq(state, query))
        return Command(
            update={
                "sub_meta": {"simulation": res.meta},
                "messages": [ToolMessage(res.message, tool_call_id=tool_call_id)],
            }
        )

    @tool
    async def ask_generator(
        query: str,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """광고 시안·카피·크리에이티브의 전략·작성 원칙·아이디어·개선 방향 조언에 답한다
        (생성 실행이 아님). 실제 생성은 run_generation.
        query에 무엇에 대한 조언인지 정리해 넣어라."""
        res = await gen(_subreq(state, query))
        return Command(
            update={
                "sub_meta": {"generator": res.meta},
                "messages": [ToolMessage(res.message, tool_call_id=tool_call_id)],
            }
        )

    # ───────────────────────── 위젯 tool (폼·목록·카드) ─────────────────────────
    @tool
    async def run_simulation(
        ad_content: str = "",
        ad_title: str = "",
        product_category: str = "",
        ad_objective: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """사용자가 광고를 '시뮬레이션 돌려달라/반응 예측해달라'고 하면 호출. 시뮬 입력 폼을 띄운다.
        발화에 있는 값만 채우고 없으면 비운다(지어내지 말 것). 폼 호출 후 한 줄로만 안내하라."""
        sim_data = {
            "ad_title": ad_title or None,
            "ad_content": ad_content or "",
            "product_category": product_category or None,
            "ad_objective": ad_objective or None,
        }
        helpers.spawn_persist(state.get("project_id"), "sim_input", sim_data)
        return Command(
            update={
                **widgets.sim_form(sim_data),
                "messages": [
                    ToolMessage("시뮬레이션 입력 폼을 준비했습니다.", tool_call_id=tool_call_id)
                ],
            }
        )

    @tool
    async def run_generation(
        product_name: str = "",
        product_description: str = "",
        target_audience: str = "",
        campaign_objective: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """사용자가 광고 '시안/카피를 만들어/생성해/뽑아'달라고 하면 호출. 생성 입력 폼을 띄운다.
        발화에 있는 값만 채우고 없으면 비운다. 폼 호출 후 한 줄로만 안내하라."""
        gen_data = {
            "product_name": product_name or None,
            "product_description": product_description or None,
            "target_audience": target_audience or None,
            "campaign_objective": campaign_objective or None,
        }
        helpers.spawn_persist(state.get("project_id"), "gen_input", gen_data)
        return Command(
            update={
                **widgets.gen_form(gen_data),
                "messages": [
                    ToolMessage("광고 생성 입력 폼을 준비했습니다.", tool_call_id=tool_call_id)
                ],
            }
        )

    @tool
    async def improve_ad_iteratively(
        product_name: str = "",
        product_description: str = "",
        target_audience: str = "",
        campaign_objective: str = "conversion",
        quality_target: float = 0.8,
        max_iterations: int = 3,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """폼 없이 '알아서 좋은 시안까지 뽑아/반복 개선해줘'처럼 자동 개선 루프를 원할 때 호출한다.
        QA 품질이 목표에 도달할 때까지 생성→평가→개선을 자동 반복한다(백그라운드+진행 카드).
        단발 '시안 만들어줘'는 run_generation 폼을 쓴다. 발화의 값만 채우고 없으면 비운다."""
        import uuid as _uuid  # noqa: PLC0415

        from domain.generator.service import generation_loop  # noqa: PLC0415

        if not (product_name and product_description and target_audience):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "자동 개선 루프를 돌리려면 상품명·설명·타깃이 필요해요. "
                            "알려주시면 바로 시작할게요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        created_by = None
        uid = state.get("user_id")
        if uid:
            try:
                created_by = _uuid.UUID(str(uid))
            except (ValueError, TypeError):
                created_by = None
        loop_id = await generation_loop.start_loop(
            {
                "product_name": product_name,
                "product_description": product_description,
                "target_audience": target_audience,
                "campaign_objective": campaign_objective or "conversion",
            },
            quality_target=quality_target,
            max_iterations=max(1, min(max_iterations, 5)),
            project_id=state.get("project_id"),
            created_by=created_by,
        )
        stream_url = f"/api/generator/generations/loop/{loop_id}/stream"
        return Command(
            update={
                **widgets.gen_loop(loop_id, stream_url),
                "messages": [
                    ToolMessage(
                        "자동 개선 루프를 시작했어요. 진행 상황은 카드에서 확인하세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool
    async def list_my_simulations(
        select: bool = False,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """내가 돌린 시뮬레이션 '목록'을 보여준다. 개선하려고 하나 '고르는' 맥락이면 select=True."""
        items = await list_simulations(state.get("project_id") or "", limit=5)
        mode = "select" if select else "read"
        notice = (
            "개선할 시뮬레이션을 골라주세요."
            if select
            else ("최근 시뮬레이션 목록이에요." if items else "아직 돌린 시뮬레이션이 없어요.")
        )
        return Command(
            update={
                **widgets.sim_list(items, mode),
                "messages": [ToolMessage(notice, tool_call_id=tool_call_id)],
            }
        )

    @tool
    async def list_my_generations(
        select: bool = False,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """내가 만든 광고 시안 '목록'을 보여준다.
        이어서 작업하려고 '고르는' 맥락이면 select=True."""
        items = await list_generations(state.get("project_id") or "", limit=5)
        mode = "select" if select else "read"
        notice = (
            "이어서 작업할 생성을 골라주세요."
            if select
            else ("최근 광고 생성 목록이에요." if items else "아직 만든 시안이 없어요.")
        )
        return Command(
            update={
                **widgets.gen_list(items, mode),
                "messages": [ToolMessage(notice, tool_call_id=tool_call_id)],
            }
        )

    @tool
    async def compare_simulations(
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """기존 시뮬레이션 2개를 '비교'하려 할 때 호출. 다중선택(compare) 목록 위젯을 띄운다."""
        items = await list_simulations(state.get("project_id") or "", limit=5)
        notice = (
            "비교할 시뮬레이션을 2개 선택하세요." if items else "비교할 시뮬레이션이 아직 없어요."
        )
        return Command(
            update={
                **widgets.sim_list(items, "compare"),
                "messages": [ToolMessage(notice, tool_call_id=tool_call_id)],
            }
        )

    @tool
    async def generate_report(
        period: str = "all",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """시뮬 결과를 'PDF·리포트·보고서로 뽑아/다운로드'하려 할 때 호출. 다운로드 버튼을 띄운다.
        '이번 달'이면 period='month', 그 외 전체면 'all'."""
        p = "month" if period == "month" else "all"
        return Command(
            update={
                **widgets.report_ready(state.get("project_id"), p),
                "messages": [
                    ToolMessage(
                        "리포트를 준비했어요. 아래 버튼으로 다운로드하세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool
    async def batch_simulation(
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """새 광고 '여러 버전(2~4개)을 한 번에 비교'하려 할 때 호출. 배치 시뮬 입력 폼을 띄운다."""
        return Command(
            update={
                **widgets.batch_sim_form(),
                "messages": [
                    ToolMessage(
                        "여러 광고를 한 번에 비교할게요. 아래에 입력하고 실행하세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool
    async def create_campaign(
        name: str = "",
        objective: str = "",
        total_budget_krw: int = 0,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """사용자가 '새 광고 캠페인을 만들어'달라고 하면 호출. 생성 폼 카드를 띄운다.
        objective=traffic(클릭)|leads(전환). 예산은 원 단위 정수('5만원'=50000)."""
        prefill: dict = {}
        if name:
            prefill["name"] = name
        if objective in ("traffic", "leads"):
            prefill["objective"] = objective
        if total_budget_krw:
            prefill["total_budget_krw"] = total_budget_krw
        return Command(
            update={
                **widgets.create_campaign(prefill),
                "messages": [
                    ToolMessage(
                        "새 캠페인 생성 폼을 준비했어요. 값을 확인하고 승인해 주세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool
    async def manage_campaign(
        action: str,
        campaign_id: str = "",
        campaign_name: str = "",
        new_daily_budget_krw: int = 0,
        pct: int = 0,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """기존 캠페인 '일시중지/게재 시작/예산 증액·감액' 요청에 호출. 조치 확인 카드를 띄운다.
        action='pause'|'activate'|'increase_budget'|'decrease_budget'. 알면 campaign_id."""
        if action not in _VALID_CAMPAIGN_ACTIONS:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "어떤 조치인지 명확하지 않아요. 무엇을(중지/게재/예산 변경) "
                            "어느 캠페인에 할지 다시 알려 주세요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        payload: dict = {"action": action}
        if campaign_id:
            payload["campaign_id"] = campaign_id
        if campaign_name:
            payload["campaign_name"] = campaign_name
        if new_daily_budget_krw:
            payload["new_daily_budget_krw"] = new_daily_budget_krw
        if pct:
            payload["pct"] = pct
        return Command(
            update={
                **widgets.campaign_action(payload),
                "messages": [
                    ToolMessage(
                        "조치 확인 카드를 준비했어요. 확인해 주세요.", tool_call_id=tool_call_id
                    )
                ],
            }
        )

    @tool
    async def load_template(
        name: str,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """저장된 템플릿 이름으로 시뮬/생성 폼을 채워 띄운다('여름 캠페인 템플릿으로 …')."""
        tpl = await history.get_template_by_name(state.get("project_id"), name)
        if tpl is None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"'{name}' 템플릿을 찾지 못했어요. '내 템플릿 보여줘'로 확인해보세요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        frag = (
            widgets.sim_form(tpl["content"])
            if tpl["template_type"] == "sim"
            else widgets.gen_form(tpl["content"])
        )
        return Command(
            update={
                **frag,
                "messages": [
                    ToolMessage(
                        f"'{tpl['name']}' 템플릿으로 채웠어요. 확인·수정 후 실행하세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    # ── 텍스트 tool (위젯 없음, LLM이 결과 전달) ──
    @tool
    async def show_templates(*, state: Annotated[dict, InjectedState]) -> str:
        """저장된 입력 '템플릿 목록'을 보여준다('내 템플릿 보여줘')."""
        tpls = await history.list_templates(state.get("project_id"))
        if not tpls:
            return "아직 저장된 템플릿이 없어요. '이 설정 저장해줘'로 만들 수 있어요."
        lines = "\n".join(
            f"- {t['name']} ({'시뮬' if t['template_type'] == 'sim' else '생성'})" for t in tpls
        )
        return "저장된 템플릿이에요.\n" + lines

    @tool
    async def save_template(
        name: str = "",
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """최근 시뮬/생성 입력을 '템플릿으로 저장'한다('이 설정 저장해줘').
        name이 없으면 자동 명명."""
        project_id = state.get("project_id")
        recent = await history.get_long_term_memory(project_id, limit=5)
        latest = next(
            (m for m in recent if m.get("memory_type") in ("sim_input", "gen_input")), None
        )
        if latest is None:
            return "저장할 설정이 없어요. 먼저 시뮬레이션이나 생성을 한 번 진행해주세요."
        ttype = "sim" if latest["memory_type"] == "sim_input" else "gen"
        content = latest.get("content") or {}
        final_name = (
            name
            or content.get("ad_title")
            or content.get("product_name")
            or ("시뮬 설정" if ttype == "sim" else "생성 설정")
        )
        final_name = str(final_name)[:80]
        saved = await history.save_template(project_id, final_name, ttype, content)
        if not saved:
            return "템플릿 저장에 실패했어요. 잠시 후 다시 시도해주세요."
        return (
            f"'{final_name}' 템플릿으로 저장했어요. "
            f"다음엔 '{final_name} 템플릿으로 시뮬 돌려줘'처럼 쓰세요."
        )

    @tool
    async def show_brand(*, state: Annotated[dict, InjectedState]) -> str:
        """현재 저장된 '브랜드 설정'을 보여준다('브랜드 설정 보여줘')."""
        brand = await history.get_brand_profile(state.get("project_id"))
        return helpers.brand_show_text(brand)

    @tool
    async def extract_brand(
        brand_name: str = "",
        tone: str = "",
        target_audience: str = "",
        product_category: str = "",
        keywords: list[str] | None = None,
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """사용자가 브랜드 설정(타깃·톤·카테고리·키워드 등)을 알려줄 때 호출해 저장한다.
        발화에 언급된 항목만 채운다."""
        project_id = state.get("project_id")
        if not project_id:
            return "브랜드 설정을 저장할 프로젝트가 없어요."
        payload = {
            "brand_name": brand_name,
            "tone": tone,
            "target_audience": target_audience,
            "product_category": product_category,
            "keywords": keywords or [],
        }
        try:
            await history.upsert_brand_profile(project_id, payload)
        except Exception as exc:  # noqa: BLE001 — 저장 실패가 대화를 막지 않게
            print(f"[chat] brand upsert error: {exc!r}")
            return "브랜드 설정을 기억하지 못했어요. 잠시 후 다시 알려주세요."
        return "브랜드 설정을 기억했어요."

    # ───────────────────────── 메모리 tool (장기기억) ─────────────────────────
    @tool
    async def remember(
        fact: str,
        kind: str = "semantic",
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """다음 대화에서도 기억할 사용자 선호·결정·반복 관심을 장기기억에 저장한다.
        일회성 정보·인사·잡담은 저장하지 않는다. kind=semantic|episodic|profile."""
        user_id = state.get("user_id")
        fact = (fact or "").strip()
        if not (memory and user_id and fact):
            return "저장 생략(내용 없음/비로그인)."
        key = f"{kind}:{hashlib.sha1(fact.encode()).hexdigest()[:16]}"
        await memory.remember(state.get("org_id"), user_id, key, {"kind": kind, "fact": fact})
        return "기억했습니다."

    @tool
    async def recall(
        query: str,
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """과거 세션에서 저장한 사용자 장기기억을 의미 기반으로 조회한다."""
        user_id = state.get("user_id")
        if not (memory and user_id):
            return "(저장된 기억 없음)"
        rows = await memory.recall(state.get("org_id"), user_id, query=query, limit=5)
        facts = [r.get("fact") for r in rows if r.get("fact")]
        return "\n".join(f"- {f}" for f in facts) or "(저장된 기억 없음)"

    # ───────────────────────── 매니지먼트 이상 상담 (위임: domain/management/remediation) ──
    @tool
    async def consult_anomaly(
        campaign_id: str = "",
        campaign_name: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """캠페인이 '왜 안 좋은지/이상 있는지/문제 없는지' 물으면 호출. 서버 실측으로
        재검증해 이상이면 조치 옵션을, 정상이면 정상 확인을 답한다. 이름만 알면 campaign_name."""
        from domain.management.remediation.advisor import (  # noqa: PLC0415
            consult,
            find_campaign_id,
        )

        cid = campaign_id or (
            await find_campaign_id(settings, campaign_name) if campaign_name else None
        )
        if not cid:
            text_out = "캠페인을 특정하지 못했어요. 캠페인 이름이나 ID를 알려 주세요."
        else:
            res = await consult(settings, cid)
            if res is None:
                text_out = "실측 조회에 실패해 지금은 확인할 수 없어요. 잠시 후 다시 시도해 주세요."
            else:
                text_out = res.message
                if res.options:
                    # 기계가독 매핑 — LLM이 번호→도구를 오매핑하지 않게 명시(meta 미영속의 보완).
                    mapping = ", ".join(
                        f"{o.index}={o.action.value}({o.tool_hint or '관망'})" for o in res.options
                    )
                    text_out += f"\n\n[옵션-도구 매핑 · campaign_id={cid}] {mapping}"
        return Command(update={"messages": [ToolMessage(text_out, tool_call_id=tool_call_id)]})

    @tool
    async def recall_history(
        query: str,
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """이 프로젝트에서 과거 수행한 시뮬/생성/매니지먼트 실행 이력을 키워드로 조회한다.
        '지난번 20대 시뮬 뭐였지'처럼 과거에 무엇을 언제 돌렸는지가 필요할 때 호출한다."""
        rows = await history.search_execution_history(state.get("project_id"), query, k=5)
        if not rows:
            return "(수행 이력 없음)"
        labels = {"simulation": "시뮬", "generation": "생성", "management": "매니지먼트"}
        lines = []
        for r in rows:
            when = (r.get("executed_at") or "")[:16].replace("T", " ")
            feat = labels.get(r.get("feature_type"), r.get("feature_type") or "")
            lines.append(f"- [{when}] {feat}: {(r.get('summary') or '').strip()[:120]}")
        return "\n".join(lines)

    return [
        ask_management,
        ask_simulation,
        ask_generator,
        run_simulation,
        run_generation,
        improve_ad_iteratively,
        list_my_simulations,
        list_my_generations,
        compare_simulations,
        generate_report,
        batch_simulation,
        create_campaign,
        manage_campaign,
        consult_anomaly,
        load_template,
        show_templates,
        save_template,
        show_brand,
        extract_brand,
        remember,
        recall,
        recall_history,
    ]
