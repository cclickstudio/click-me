# 생성 채팅 서브에이전트 — 결정론 슬롯필링 루프(부족하면 되묻고, 채워지면 트리거)
"""대화에서 생성 파라미터를 모아 generator_service.start_generation을 트리거한다.

루프 종류 = 결정론(코드가 종료 판정). 반복·종료는 '필수 슬롯이 다 찼나'로 결정하고,
LLM은 추출만 한다. 자율 ReAct가 아니라 예측가능(G5).
- 부족: action=ASK(되묻기)
- 충족: action=TRIGGER + started_event(생성 SSE 핸드오프)
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from core.assistant_contracts import (
    Action,
    ProjectRef,
    StartedEvent,
    SubagentRequest,
    SubagentResult,
)
from core.schemas import ChatMessage
from domain.generator.chat.contracts import REQUIRED_SLOTS, SLOT_PROMPTS, ExtractedSlots
from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.schemas import GenerationCreateRequest

Extractor = Callable[[list[ChatMessage]], Awaitable[ExtractedSlots]]
Starter = Callable[..., Awaitable[str]]

_META = {"source": "generator", "label": "생성 어시스턴트", "engine": "Gemini · 슬롯필링"}

_GEMINI_MODEL = "gemini-2.5-flash"

_EXTRACT_SYSTEM = (
    "너는 광고 생성 요청에서 파라미터를 추출하는 도우미다. 대화 전체를 읽고 아래 필드를 채워라.\n"
    "- product_name: 광고할 상품·서비스 이름\n"
    "- product_description: 핵심 특징·장점\n"
    "- target_audience: 타깃 고객(예시 — 20대 여성)\n"
    "- campaign_objective: conversion|awareness|traffic 중 언급된 것\n"
    "- format: single|carousel 중 언급된 것\n"
    "- project_hint: 사용자가 지목한 프로젝트 이름이나 번호\n"
    "언급되지 않은 필드는 빈 문자열로 둔다. 절대 추정하거나 지어내지 마라."
)


def _build_gemini_extractor(settings) -> Extractor | None:
    """Gemini 구조화 출력 추출기. 키 없으면 None(폴백 — 항상 되묻기)."""
    api_key = getattr(settings, "gemini_api_key", None)
    if not api_key:
        return None

    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415 — 키 있을 때만 로드

    model = getattr(settings, "chat_model", _GEMINI_MODEL)
    llm = ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0.0)
    structured = llm.with_structured_output(ExtractedSlots)

    async def _extract(messages: list[ChatMessage]) -> ExtractedSlots:
        history = "\n".join(f"{m.role}: {m.content}" for m in messages[-10:])
        return await structured.ainvoke(
            [("system", _EXTRACT_SYSTEM), ("human", history)],
            config={"run_name": "generator.chat.extract_slots"},
        )

    return _extract


def _match_project(hint: str, projects: list[ProjectRef]) -> ProjectRef | None:
    """힌트(이름/번호)를 후보 프로젝트에 매칭. 없으면 None."""
    hint = hint.strip()
    if not hint or not projects:
        return None
    # 번호 지목(1-based)
    digits = "".join(c for c in hint if c.isdigit())
    if digits:
        idx = int(digits) - 1
        if 0 <= idx < len(projects):
            return projects[idx]
    # 이름 부분일치
    low = hint.lower()
    for p in projects:
        if low in p.name.lower() or p.name.lower() in low:
            return p
    return None


def _ask_for_slots(missing: list[str]) -> str:
    lines = "\n".join(f"- {SLOT_PROMPTS[s]}" for s in missing)
    return f"광고를 만들려면 다음 정보가 필요해요.\n{lines}"


def _ask_for_project(req: SubagentRequest) -> str:
    if not req.available_projects:
        if not req.user_id:
            return (
                "결과를 저장하려면 로그인 후 프로젝트를 선택해야 해요. 로그인 상태를 확인해 주세요."
            )
        return "저장할 프로젝트가 아직 없어요. 프로젝트를 먼저 만든 뒤 다시 요청해 주세요."
    names = "\n".join(f"{i + 1}. {p.name}" for i, p in enumerate(req.available_projects))
    return f"생성 결과를 저장할 프로젝트를 골라주세요.\n{names}"


def _confirm(slots: ExtractedSlots) -> str:
    return f"'{slots.product_name}' 광고 시안 생성을 시작했어요. 진행 상황은 곧 표시됩니다."


def build_generation_chat_agent(
    settings, *, extractor: Extractor | None = None, starter: Starter | None = None
):
    """async handle(SubagentRequest) -> SubagentResult. 오케스트레이터가 generate로 디스패치."""
    if extractor is None:
        extractor = _build_gemini_extractor(settings)
    if starter is None:
        from domain.generator.service import generator_service  # noqa: PLC0415

        starter = generator_service.start_generation

    async def handle(req: SubagentRequest) -> SubagentResult:
        slots = await extractor(req.messages) if extractor else ExtractedSlots()

        # 1) 필수 콘텐츠 슬롯 먼저 — 부족하면 되묻기
        missing = [s for s in REQUIRED_SLOTS if not getattr(slots, s).strip()]
        if missing:
            return SubagentResult(action=Action.ASK, message=_ask_for_slots(missing), meta=_META)

        # 2) 저장 프로젝트 해결 — 프론트 지정 > 힌트 매칭 > 되묻기
        project_id = req.project_id
        if not project_id:
            matched = _match_project(slots.project_hint, req.available_projects)
            if matched:
                project_id = matched.id
        if not project_id:
            return SubagentResult(action=Action.ASK, message=_ask_for_project(req), meta=_META)

        # 3) 전부 충족 — 생성 트리거 + 핸드오프
        gen_req = GenerationCreateRequest(
            mode=GenerationMode.CREATE,
            project_id=project_id,
            product_name=slots.product_name,
            product_description=slots.product_description,
            target_audience=slots.target_audience,
            campaign_objective=slots.campaign_objective or "conversion",
            format=slots.format or "single",
        )
        created_by = uuid.UUID(req.user_id) if req.user_id else None
        generation_id = await starter(gen_req, created_by=created_by)
        started = StartedEvent(
            event="generation_started",
            job_id=generation_id,
            stream_url=f"/api/generator/generations/{generation_id}/stream",
            domain="generator",
        )
        return SubagentResult(
            action=Action.TRIGGER, message=_confirm(slots), meta=_META, started_event=started
        )

    return handle
