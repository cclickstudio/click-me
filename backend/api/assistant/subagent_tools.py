# 통합 채팅 에이전트 tool 모음 — LLM이 정책(prompts.py)에 따라 호출하는 액션·위임·메모리 도구
"""tool이 실행을 담당하고 판단은 LLM이 한다(정책=프롬프트).

위임 tool은 wiring.py의 도메인 핸들러(SubagentRequest→SubagentResult)를 재사용한다.
위젯 tool은 widgets.py 형태를 Command(update=...)로 상태에 적재 — 슬롯은 LLM이 인자로 추출한다.
per-turn 컨텍스트(session_id·project_id…)는 InjectedState로 읽는다(closure로 못 잡는 값).
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from api.assistant import improve_context
from api.assistant.contracts import SubagentRequest
from api.assistant.wiring import (
    _build_generator_handler,
    _build_management_handler,
    _build_simulation_handler,
)
from core.schemas import ChatMessage
from domain.chat import helpers, history, widgets
from domain.generator.assistant.tools import (
    fetch_generation_result,
    list_generations,
    start_improve_generation,
)
from domain.generator.assistant.tools import (
    run_generation as start_generation_now,
)
from domain.simulation.assistant.tools import list_simulations
from domain.simulation.assistant.tools import run_simulation as sim_run_simulation

_VALID_CAMPAIGN_ACTIONS = ("pause", "activate", "increase_budget", "decrease_budget")

# 자동 개선 루프의 최초 1회 시뮬(eval_mode=simulation) 표본 — 저비용 진단용.
_LOOP_SIM_SAMPLE = 12


async def _loop_simulate(candidate: dict, seed: dict) -> dict | None:
    """루프 최초 시안의 카피로 시뮬 1회(텍스트) → 4대 KPI. generator 도메인이 simulation을 직접
    import하지 않도록, 조립은 여기(api/assistant)서 하고 generation_loop엔 콜백으로 주입한다."""
    copy = candidate.get("copy") or {}
    ad_content = "\n".join(
        p for p in (copy.get("headline"), copy.get("body"), copy.get("cta")) if p
    ) or (seed.get("product_description") or "")
    if not ad_content:
        return None
    try:
        return await sim_run_simulation(
            ad_content=ad_content,
            ad_title=copy.get("headline") or seed.get("product_name"),
            ad_objective=seed.get("campaign_objective"),
            sample_size=_LOOP_SIM_SAMPLE,
        )
    except Exception:  # noqa: BLE001 — 시뮬 실패는 루프가 QA-only로 폴백
        return None


# 실행 히스토리 summary용 한글 라벨 — BM25(공백 토큰) 서치가 한국어 질의에 잡히게.
_CAMPAIGN_ACTION_LABELS = {
    "pause": "일시중지",
    "activate": "게재 시작",
    "increase_budget": "예산 증액",
    "decrease_budget": "예산 감액",
}

# 일반 지식 KB 게이트 — top cosine이 이 미만이면 근거 불충분(구 ADVISE 게이트와 동일 취지).
_GENERAL_KB_THRESHOLD = 0.35


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


def build_chat_tools(settings, clio_retriever=None) -> list:
    """통합 채팅 에이전트에 등록할 tool 리스트를 빌드한다(settings·핸들러 클로저).

    clio_retriever는 테스트 주입용 — None이면 풀모드(키 존재·use_mock=False)에서만 내부 생성.
    """
    mgmt = _build_management_handler(settings)
    gen = _build_generator_handler(settings)
    sim = _build_simulation_handler(settings)

    clio = clio_retriever
    if clio is None:
        api_key = getattr(settings, "openai_api_key", None)
        if api_key and not getattr(settings, "use_mock", True):
            from domain.chat.retriever import ClioKbRetriever  # noqa: PLC0415

            clio = ClioKbRetriever(api_key=api_key)

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
        벤치마크, 주간 리포트·예산 리밸런싱·이상/피로 스캔·플랫폼/연령성별 분해·캠페인 시안·
        타게팅·리드 명단·오가닉 대비 증분 비교까지. query에는 사용자의 질문을 명확히 정리해
        넣어라."""
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

    @tool
    async def ask_general_knowledge(
        query: str,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """특정 캠페인·시안·시뮬과 무관한 광고·마케팅 '일반 지식·용어 정의·업계 개념' 질문에
        근거 문서를 검색한다(예: 'CPM이 뭐야', '어트리뷰션 모델 종류'). 검색 결과를 근거로
        네가 종합해 답하라. 행위 조언(어떻게 쓸까/만들까)은 ask_generator를 쓴다."""
        _ = state  # per-turn 컨텍스트 불필요 — 시그니처는 다른 ask_*와 통일
        if clio is None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "일반 지식베이스를 사용할 수 없는 환경이야. "
                            "아는 범위에서 신중히 답하되 불확실하면 모른다고 답하라.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        try:
            hits = await clio.search(query, k=4)
        except Exception:  # noqa: BLE001 — KB 미적재·일시 오류는 빈 결과로 진행
            hits = []
        top_cosine = max((h.get("cosine_score") or 0.0 for h in hits), default=0.0)
        if not hits or top_cosine < _GENERAL_KB_THRESHOLD:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "지식베이스에 충분한 근거가 없어. 아는 범위에서 신중히 답하되 "
                            "불확실하면 모른다고 답하라.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        ctx = "\n\n".join(f"[{i + 1}] {h['title']}\n{h['chunk']}" for i, h in enumerate(hits))
        citations = [{"kind": "kb", "source": h["source"], "title": h["title"]} for h in hits]
        return Command(
            update={
                "sub_meta": {
                    "clio": {
                        "source": "clio",
                        "label": "광고 지식 베이스",
                        "citations": citations,
                    }
                },
                "messages": [
                    ToolMessage(
                        "아래 지식베이스 근거로 답하라. 근거에 없는 내용은 지어내지 말 것.\n\n"
                        + ctx,
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    # ───────────────────────── 위젯 tool (폼·목록·카드) ─────────────────────────
    @tool
    async def run_simulation(
        ad_content: str = "",
        ad_title: str = "",
        product_category: str = "",
        ad_objective: str = "",
        analysis_mode: str = "synthetic",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """사용자가 광고를 '시뮬레이션 돌려달라/반응 예측해달라'고 하면 호출. 시뮬 입력 폼을 띄운다.
        발화에 있는 값만 채우고 없으면 비운다(지어내지 말 것). 폼 호출 후 한 줄로만 안내하라.

        analysis_mode(3-모드 분석) — 기본 synthetic(표본 전체 합성). 사용자가 '한 명만 자세히'·
        '개인 반응'·'심층 분석'처럼 개별 페르소나를 원하면 individual. '세그먼트별로 비교'·
        '타깃별로 나눠서'처럼 여러 집단 비교를 원하면 persona_set(폼은 세그먼트 편집이 필요해
        채팅에선 미지원 — 이땐 폼을 띄우지 말고 /simulation 페이지 이용을 안내하라)."""
        sim_data = {
            "ad_title": ad_title or None,
            "ad_content": ad_content or "",
            "product_category": product_category or None,
            "ad_objective": ad_objective or None,
            "analysis_mode": analysis_mode
            if analysis_mode in ("synthetic", "individual")
            else "synthetic",
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
        skip_product_image: bool = False,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """사용자가 광고 '시안/카피를 만들어/생성해/뽑아'달라고 하면 호출.
        발화에 있는 값만 채우고 없으면 비운다(지어내기 금지).
        상품명·설명·타깃이 모두 있으면 폼 없이 바로 생성이 시작된다(진행 카드).
        단, 상품 이미지 의사를 모르면 시작 전에 묻는다 — 사용자가 '이미지 없이/그냥 진행'
        이라 했거나 무형 상품(서비스·앱 등)이면 skip_product_image=True로 호출하라.
        이미지를 첨부한 턴이면 첨부가 상품 이미지로 쓰이는 폼이 뜬다.
        호출 후 한 줄로만 안내하라."""
        gen_data = {
            "product_name": product_name or None,
            "product_description": product_description or None,
            "target_audience": target_audience or None,
            "campaign_objective": campaign_objective or None,
        }
        helpers.spawn_persist(state.get("project_id"), "gen_input", gen_data)
        project_id = state.get("project_id")
        complete = bool(product_name and product_description and target_audience and project_id)
        # 완비 + 이번 턴 이미지 첨부 → 폼 경로(첨부가 상품 이미지로 프리필됨, 실행만 누르면 됨)
        if complete and state.get("has_image"):
            return Command(
                update={
                    **widgets.gen_form(gen_data),
                    "messages": [
                        ToolMessage(
                            "첨부하신 이미지를 상품 이미지로 쓰는 생성 폼을 준비했어요. "
                            "내용 확인 후 실행만 누르면 됩니다.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )
        # 완비지만 이미지 의사 미확인 → 시작하지 않고 되묻는다(형태 없는 상품은 없이 진행 가능)
        if complete and not skip_product_image:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "생성 준비가 끝났어요. 시작 전에 사용자에게 상품 이미지를 넣을지 "
                            "물어보라 — 넣으려면 이미지를 첨부해 답하고, 서비스처럼 형태가 "
                            "없거나 원치 않으면 '이미지 없이 진행'이라 답하면 된다고 안내하라.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        # 완비 + 이미지 없이 진행 확정 → 폼 스킵 즉시 실행(진행 카드로 관찰)
        if complete:
            started = await start_generation_now(
                product_name=product_name,
                product_description=product_description,
                target_audience=target_audience,
                campaign_objective=campaign_objective or "conversion",
                project_id=project_id,
                created_by=str(state.get("user_id")) if state.get("user_id") else None,
            )
            return Command(
                update={
                    **widgets.gen_progress(started["generation_id"], started["stream_url"]),
                    "messages": [
                        ToolMessage(
                            "광고 생성을 바로 시작했어요. 진행 상황은 카드에서 확인하세요.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )
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
        use_simulation: bool = False,
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """폼 없이 '알아서 좋은 시안까지 뽑아/반복 개선해줘'처럼 자동 개선 루프를 원할 때 호출한다.
        QA 품질이 목표에 도달할 때까지 생성→평가→개선을 자동 반복한다(백그라운드+진행 카드).
        '시뮬(레이션) 기준으로/소비자 반응 반영해서 반복 개선'처럼 명시하면 use_simulation=True로
        호출하라 — 최초 시안에 시뮬 1회를 돌려 소비자 반응 기반 개선 방향을 잡는다(그 외엔 False).
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
        # 시뮬 모드는 반복당 비용을 최초 1회로 묶되 반복 수도 보수적으로(기본 2).
        iters = (
            max(1, min(max_iterations, 5)) if not use_simulation else max(1, min(max_iterations, 2))
        )
        loop_id = await generation_loop.start_loop(
            {
                "product_name": product_name,
                "product_description": product_description,
                "target_audience": target_audience,
                "campaign_objective": campaign_objective or "conversion",
            },
            quality_target=quality_target,
            max_iterations=iters,
            project_id=state.get("project_id"),
            created_by=created_by,
            simulate_fn=_loop_simulate if use_simulation else None,
        )
        stream_url = f"/api/generator/generations/loop/{loop_id}/stream"
        notice = (
            "시뮬 결과를 반영해 자동 개선 루프를 시작했어요. 진행 상황은 카드에서 확인하세요."
            if use_simulation
            else "자동 개선 루프를 시작했어요. 진행 상황은 카드에서 확인하세요."
        )
        return Command(
            update={
                **widgets.gen_loop(loop_id, stream_url),
                "messages": [ToolMessage(notice, tool_call_id=tool_call_id)],
            }
        )

    @tool
    async def run_improvement(
        simulation_id: str = "",
        fix_requests: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """기존 '시뮬 결과를 반영해 개선 시안을 만들어'달라고 하면 호출(단발 1회).
        발화에 시뮬 id가 있으면 넣고, '아까/방금/최근'이면 비워라(최근 완료 시뮬 자동 선택).
        고칠 점 언급은 fix_requests로. 시뮬 프리필이 완비되면 폼 없이 바로 시작되고(진행 카드),
        아니면 개선 폼이 뜬다. 자동 반복 개선은 improve_ad_iteratively,
        시뮬 없이 새로 만들기는 run_generation. 호출 후 한 줄로만 안내하라."""
        sid = simulation_id or ""
        if not sid:
            project_id = state.get("project_id") or ""
            if not project_id:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "개선할 시뮬레이션을 찾을 프로젝트가 없어요. "
                                "프로젝트를 선택하거나 시뮬레이션을 지정해주세요.",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )
            sid = await improve_context.latest_completed_simulation_id(project_id) or ""
        gen_data = None
        if sid:
            gen_data = await improve_context.improve_gen_data_for_simulation(
                sid, fix_requests or None, org_id=state.get("org_id")
            )
        if gen_data is None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "아직 완료된 시뮬레이션이 없어요. 먼저 시뮬레이션을 돌리면 "
                            "그 결과를 반영한 개선 시안을 만들 수 있어요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        helpers.spawn_persist(state.get("project_id"), "gen_input", gen_data)
        project_id = state.get("project_id")
        # 시뮬 프리필 완비(요약·상품명) + 프로젝트 → 폼 스킵 즉시 실행(진행 카드)
        if gen_data.get("simulation_summary") and gen_data.get("product_name") and project_id:
            started = await start_improve_generation(
                gen_data,
                project_id=project_id,
                created_by=str(state.get("user_id")) if state.get("user_id") else None,
            )
            return Command(
                update={
                    **widgets.gen_progress(started["generation_id"], started["stream_url"]),
                    "messages": [
                        ToolMessage(
                            "시뮬 결과를 반영한 개선 생성을 바로 시작했어요. "
                            "진행 상황은 카드에서 확인하세요.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )
        return Command(
            update={
                **widgets.gen_form(gen_data),
                "messages": [
                    ToolMessage(
                        "시뮬 결과를 반영한 개선 생성 폼을 준비했습니다.",
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

    async def _resolve_generation(state: dict, generation_id: str) -> tuple[str, dict] | str:
        """generation_id(비면 최근 완료 생성)를 상세와 함께 해석. 실패 시 안내문 str 반환."""
        gid = (generation_id or "").strip()
        if not gid:
            items = await list_generations(state.get("project_id") or "", limit=10)
            done = [i for i in items if i.get("status") == "completed"]
            if not done:
                return "완료된 광고 생성이 없어요. 먼저 시안을 만들어주세요."
            gid = done[0]["id"]
        detail = await fetch_generation_result(gid)
        if detail.get("error"):
            return "해당 생성 결과를 찾을 수 없어요."
        return gid, detail

    @tool
    async def compare_ad_candidates(
        generation_id: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """생성한 시안 중 상위 2개를 'A/B로 비교/붙여봐/어느 게 나아' 할 때 호출.
        같은 AI 소비자 패널로 비교하도록 배치 시뮬 폼에 두 시안을 프리필한다.
        generation_id 없으면 최근 완료 생성을 쓴다. 수동 2개 비교는 batch_simulation."""
        from domain.generator.service import generator_service  # noqa: PLC0415

        resolved = await _resolve_generation(state, generation_id)
        if isinstance(resolved, str):
            return Command(update={"messages": [ToolMessage(resolved, tool_call_id=tool_call_id)]})
        gid, _ = resolved
        detail = await generator_service.get_detail(gid)
        if not detail or detail.get("status") != "completed":
            return Command(
                update={
                    "messages": [
                        ToolMessage("완료된 생성 결과를 찾지 못했어요.", tool_call_id=tool_call_id)
                    ]
                }
            )
        cands = detail.get("candidates") or []
        if len(cands) < 2:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            "A/B로 비교하려면 시안이 2개 이상 있어야 해요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        gen_input = detail.get("input") or {}
        category = gen_input.get("product_category") or gen_input.get("product_name") or ""

        def _ad(c: dict) -> dict:
            copy = c.get("copy") or {}
            title = (copy.get("headline") or "").strip()
            body = (copy.get("body") or "").strip()
            content = "\n".join(p for p in (title, body) if p) or title or body
            return {"ad_title": title, "ad_content": content, "product_category": category}

        # 상위 2개는 get_detail이 QA점수로 이미 랭크(rank)해 반환 — 앞 2개가 최상위.
        ads = [_ad(cands[0]), _ad(cands[1])]
        return Command(
            update={
                **widgets.batch_sim_form({"ads": ads}),
                "messages": [
                    ToolMessage(
                        "상위 두 시안을 같은 AI 소비자 패널로 A/B 비교하도록 준비했어요. "
                        "내용을 확인하고 실행하세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool
    async def select_ad_candidate(
        candidate_number: int = 0,
        candidate_id: str = "",
        generation_id: str = "",
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """생성된 시안 중 하나를 최종 후보로 '선택/확정'한다('2번 시안으로 확정해줘').
        번호 언급이면 candidate_number(1부터), id 언급이면 candidate_id.
        '아까/방금 만든'이면 generation_id를 비워라(최근 완료 생성 자동 선택)."""
        from domain.generator.service import generator_service  # noqa: PLC0415

        resolved = await _resolve_generation(state, generation_id)
        if isinstance(resolved, str):
            return resolved
        gid, detail = resolved
        cands = detail.get("candidates") or []
        cid = (candidate_id or "").strip()
        if not cid:
            if not 1 <= candidate_number <= len(cands):
                return f"몇 번 시안으로 확정할지 알려주세요 (1~{len(cands)}번)."
            cid = cands[candidate_number - 1]["candidate_id"]
        if not await generator_service.select_candidate(gid, cid):
            return "해당 후보를 찾지 못했어요. 시안 목록을 다시 확인해주세요."
        picked = next((c for c in cands if c.get("candidate_id") == cid), {})
        return (
            f"후보를 확정했어요 — 전략 {picked.get('strategy') or '?'}"
            f", 헤드라인 '{picked.get('headline') or ''}'. 게시를 원하시면 말씀해주세요."
        )

    @tool
    async def publish_ad_candidate(
        caption: str = "",
        generation_id: str = "",
        confirm: bool = False,
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """확정(선택)된 시안을 Instagram에 게시한다. 게시는 외부 노출이므로 사용자가
        명시적으로 동의('응 게시해')한 경우에만 confirm=True로 호출한다.
        동의 전엔 confirm=False로 호출해 게시 예정 내용을 확인시킨다."""
        from domain.generator.service import generator_service  # noqa: PLC0415

        resolved = await _resolve_generation(state, generation_id)
        if isinstance(resolved, str):
            return resolved
        gid, detail = resolved
        sel = detail.get("selected_candidate_id")
        if not sel:
            return "아직 확정된 시안이 없어요. 먼저 시안을 선택(확정)해주세요."
        picked = next(
            (c for c in (detail.get("candidates") or []) if c.get("candidate_id") == sel), {}
        )
        if not confirm:
            return (
                f"게시 준비 완료 — 확정 시안 '{picked.get('headline') or ''}'"
                f", 캡션 {caption or '(없음)'}. 인스타그램에 실제 게시됩니다. 게시할까요?"
            )
        res = await generator_service.publish_candidate(gid, sel, caption or "")
        if res is None:
            return "게시할 후보를 찾지 못했어요."
        if res.get("error") == "selected_candidate_only":
            return "선택(확정)된 후보만 게시할 수 있어요. 먼저 시안을 확정해주세요."
        status = res.get("status")
        if status == "published":
            return f"인스타그램에 게시했어요 (media_id {res.get('media_id')})."
        if status == "mocked":
            return "게시를 모의(mock) 처리했어요 — Meta 자격증명이 없어 실제 게시는 안 됐습니다."
        return f"게시에 실패했어요 — {res.get('error') or '원인 미상'}."

    @tool
    async def render_ad_for_platform(
        platform: str = "ig_feed",
        candidate_number: int = 0,
        candidate_id: str = "",
        generation_id: str = "",
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """시안을 플랫폼 규격으로 리레이아웃한 이미지 링크를 준다
        ('스토리 사이즈로', '페북 피드용으로'). platform은 ig_feed|ig_story|fb_feed|linkedin.
        후보 지정이 없으면 확정 후보(없으면 1순위)를 쓴다."""
        from domain.generator.pipeline.relayout import PLATFORM_SIZES  # noqa: PLC0415

        if platform not in PLATFORM_SIZES:
            return f"지원하는 플랫폼은 {', '.join(PLATFORM_SIZES)} 입니다."
        cid = (candidate_id or "").strip()
        if not cid:
            resolved = await _resolve_generation(state, generation_id)
            if isinstance(resolved, str):
                return resolved
            _, detail = resolved
            cands = detail.get("candidates") or []
            if 1 <= candidate_number <= len(cands):
                cid = cands[candidate_number - 1]["candidate_id"]
            else:
                cid = detail.get("selected_candidate_id") or (
                    cands[0]["candidate_id"] if cands else ""
                )
        if not cid:
            return "리레이아웃할 후보를 찾지 못했어요."
        w, h = PLATFORM_SIZES[platform]
        url = f"/api/generator/candidates/{cid}/render?platform={platform}"
        return f"{platform}({w}x{h}) 리레이아웃 이미지 링크예요 — {url} (신규 생성물부터 지원)"

    @tool
    async def download_generation_zip(
        generation_id: str = "",
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """생성된 후보 이미지 전체를 ZIP으로 받는 다운로드 링크를 준다
        ('시안 전부 다운로드/압축해줘')."""
        resolved = await _resolve_generation(state, generation_id)
        if isinstance(resolved, str):
            return resolved
        gid, detail = resolved
        n = detail.get("candidate_count", 0)
        return f"후보 {n}개 ZIP 다운로드 링크예요 — /api/generator/generations/{gid}/download-zip"

    @tool
    async def list_brand_kits(*, state: Annotated[dict, InjectedState]) -> str:
        """조직에 저장된 브랜드 키트(색·로고·톤 프리셋) 목록을 보여준다."""
        from domain.generator.service import brand_kit as brand_kit_service  # noqa: PLC0415

        org = state.get("org_id")
        if not org:
            return "조직 정보가 없어 브랜드 키트를 조회할 수 없어요."
        kits = await brand_kit_service.list_kits(str(org))
        if not kits:
            return "저장된 브랜드 키트가 없어요."
        lines = [
            f"- {k['name']} — 색 {k.get('brand_color') or '없음'}"
            f", 톤 {k.get('tone_and_manner') or '없음'}"
            f", 로고 {'있음' if k.get('brand_logo_key') else '없음'}"
            for k in kits
        ]
        return "\n".join(lines)

    @tool
    async def save_brand_kit(
        name: str,
        brand_color: str = "",
        tone_and_manner: str = "",
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """브랜드 키트를 저장한다('브랜드 키트로 저장해줘'). 같은 이름이 있으면
        말한 항목만 갱신한다(언급 없는 항목·로고는 유지). 로고 업로드는 생성 페이지에서."""
        import uuid as _uuid  # noqa: PLC0415

        from domain.generator.service import brand_kit as brand_kit_service  # noqa: PLC0415

        org = state.get("org_id")
        if not org:
            return "조직 정보가 없어 브랜드 키트를 저장할 수 없어요."
        if not name.strip():
            return "키트 이름을 알려주세요."
        kits = await brand_kit_service.list_kits(str(org))
        existing = next((k for k in kits if k["name"] == name.strip()), None)
        if existing:
            await brand_kit_service.update_kit(
                str(org),
                existing["id"],
                name=name.strip(),
                brand_color=brand_color or existing.get("brand_color"),
                brand_logo_key=existing.get("brand_logo_key"),
                tone_and_manner=tone_and_manner or existing.get("tone_and_manner"),
            )
            return f"브랜드 키트 '{name.strip()}'을(를) 갱신했어요."
        created_by = None
        uid = state.get("user_id")
        if uid:
            try:
                created_by = _uuid.UUID(str(uid))
            except (ValueError, TypeError):
                created_by = None
        await brand_kit_service.create_kit(
            str(org),
            created_by,
            name=name.strip(),
            brand_color=brand_color or None,
            tone_and_manner=tone_and_manner or None,
        )
        return f"브랜드 키트 '{name.strip()}'을(를) 저장했어요."

    @tool
    async def delete_brand_kit(name: str, *, state: Annotated[dict, InjectedState]) -> str:
        """이름으로 브랜드 키트를 삭제한다('X 키트 지워줘')."""
        from domain.generator.service import brand_kit as brand_kit_service  # noqa: PLC0415

        org = state.get("org_id")
        if not org:
            return "조직 정보가 없어 브랜드 키트를 삭제할 수 없어요."
        kits = await brand_kit_service.list_kits(str(org))
        target = next((k for k in kits if k["name"] == name.strip()), None)
        if target is None:
            return f"'{name.strip()}' 이름의 브랜드 키트를 찾지 못했어요."
        if not await brand_kit_service.delete_kit(str(org), target["id"]):
            return "브랜드 키트 삭제에 실패했어요."
        return f"브랜드 키트 '{name.strip()}'을(를) 삭제했어요."

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
        # 실행 히스토리 적재 — 폼 시점 = '요청' 기록(실행 확정은 executor가 별도 기록).
        # 승인 없이 닫혀도 남으므로 action·summary에 요청임을 명시해 거짓 양성을 막는다.
        helpers.spawn_record_execution(
            state.get("project_id"),
            "management",
            "create_campaign_request",
            f"캠페인 생성 요청(폼) {name} 목표 {objective} 예산 {total_budget_krw}원",
            {**prefill, "stage": "request"},
        )
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
        # 실행 히스토리 적재 — 폼 시점 = '요청' 기록(실행 확정은 executor가 별도 기록).
        helpers.spawn_record_execution(
            state.get("project_id"),
            "management",
            f"{action}_request",
            f"캠페인 조치 요청(폼) {_CAMPAIGN_ACTION_LABELS.get(action, action)} "
            f"{campaign_name or campaign_id} "
            f"{f'일예산 {new_daily_budget_krw}원' if new_daily_budget_krw else ''}"
            f"{f'{pct}%' if pct else ''}".strip(),
            {**payload, "stage": "request"},
        )
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
    async def replace_creative(
        campaign_id: str = "",
        campaign_name: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """기존 캠페인의 '광고 소재(이미지·카피)를 교체'해달라는 요청에 호출.
        내가 만든 광고 시안 후보를 고르는 picker 카드를 띄운다.
        캠페인을 알면 campaign_id 또는 campaign_name(이름만 알아도 됨)."""
        helpers.spawn_record_execution(
            state.get("project_id"),
            "management",
            "replace_creative_request",
            f"소재 교체 요청(폼) 캠페인 {campaign_name or campaign_id or '(미지정)'}",
            {"campaign_id": campaign_id, "campaign_name": campaign_name, "stage": "request"},
        )
        return Command(
            update={
                **widgets.replace_creative_form(campaign_id, campaign_name),
                "messages": [
                    ToolMessage(
                        "소재 교체 후보를 고를 수 있는 카드를 준비했어요.",
                        tool_call_id=tool_call_id,
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
        # 최근 실행 히스토리(롱텀 메모리)에서 마지막 시뮬/생성 입력을 찾는다(빈 query = 최신순).
        recent = await history.search_execution_history(project_id, "", k=5)
        latest = next(
            (r for r in recent if r.get("feature_type") in ("simulation", "generation")), None
        )
        if latest is None:
            return "저장할 설정이 없어요. 먼저 시뮬레이션이나 생성을 한 번 진행해주세요."
        ttype = "sim" if latest["feature_type"] == "simulation" else "gen"
        content = latest.get("payload") or {}
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

    # ───────────────────── 롱텀 메모리 tool (실행 히스토리) ─────────────────────
    @tool
    async def recall_history(
        query: str = "",
        feature_type: str = "",
        date_from: str = "",
        date_to: str = "",
        *,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """이 프로젝트에서 과거 수행한 시뮬/생성/매니지먼트 실행 이력(롱텀 메모리)을 조회한다.
        '지난번 20대 시뮬 뭐였지'처럼 과거에 무엇을 언제 돌렸는지가 필요할 때 호출한다.
        query는 키워드(비우면 최신순). feature_type=simulation|generation|management(선택).
        '6월 20일에 뭐 돌렸지'처럼 시점 질문이면 date_from/date_to를 YYYY-MM-DD로 채운다
        (하루면 둘 다 같은 날짜)."""
        rows = await history.search_execution_history(
            state.get("project_id"),
            query,
            k=5,
            feature_type=feature_type or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
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
        ask_general_knowledge,
        run_simulation,
        run_generation,
        run_improvement,
        improve_ad_iteratively,
        list_my_simulations,
        list_my_generations,
        select_ad_candidate,
        publish_ad_candidate,
        render_ad_for_platform,
        download_generation_zip,
        list_brand_kits,
        save_brand_kit,
        delete_brand_kit,
        compare_simulations,
        generate_report,
        batch_simulation,
        compare_ad_candidates,
        create_campaign,
        manage_campaign,
        replace_creative,
        consult_anomaly,
        load_template,
        show_templates,
        save_template,
        show_brand,
        extract_brand,
        recall_history,
    ]
