# 최상위 의도 분류 — Gemini 계측 1콜(LangSmith 기록), 키 없으면 키워드 폴백
"""결정론 우선(테스트 가능). 등록된 의도(registered)만 후보로 두고, 나머지는 advise로 폴백한다.

- 실모드: Gemini 구조화 출력으로 분류(계측 → LangSmith).
- 폴백/테스트: 키워드 규칙. generate를 먼저 보고(만들/생성), 그다음 manage, 아니면 advise.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from api.assistant.contracts import Intent, SubagentRequest

# 생성 의도 신호 — manage("광고")와 겹치므로 먼저 검사한다.
_GENERATE_KW: frozenset[str] = frozenset(
    {"만들", "생성", "제작", "시안", "디자인해", "카피 써", "카피 작성", "새 광고", "광고 만"}
)
# 매니지먼트 신호(chat.py 기존 키워드와 동일 계열).
_MANAGE_KW: frozenset[str] = frozenset(
    {
        "캠페인",
        "예산",
        "소진",
        "런레이트",
        "페이싱",
        "게재",
        "roas",
        "ctr",
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
        "cpm",
        "cpc",
        "벤치마크",
        "메타",
        "틱톡",
        "구글",
        "네이버",
        "카카오",
        "업종",
        "연령대",
        "구매의향",
        "입찰",
        "타깃",
        "타겟",
        "오디언스",
    }
)


class _IntentPick(BaseModel):
    """LLM 구조화 출력 — 단일 의도."""

    intent: Intent


def _keyword_classify(text: str, registered: Sequence[Intent]) -> Intent:
    low = text.lower()
    if Intent.GENERATE in registered and any(k in low for k in _GENERATE_KW):
        return Intent.GENERATE
    if Intent.MANAGE in registered and any(k in low for k in _MANAGE_KW):
        return Intent.MANAGE
    return Intent.ADVISE


async def _llm_classify(llm, req: SubagentRequest, registered: Sequence[Intent]) -> Intent:
    allowed = ", ".join([*[i.value for i in registered], Intent.ADVISE.value])
    system = (
        "너는 광고 플랫폼 채팅의 의도 분류기다. 사용자의 마지막 메시지를 다음 중 하나로 분류한다.\n"
        f"허용 라벨: {allowed}.\n"
        "- generate: 새 광고/시안/카피/이미지를 만들어 달라는 요청.\n"
        "- manage: 광고 운영 도메인 전반 — 집행 캠페인의 예산·성과·상태 조회나 운영 변경뿐 아니라, "
        "광고 성과·정책·심사·최적화·빈도·CTR/CPM/ROAS·벤치마크·타깃·소재·플랫폼(메타/구글/틱톡)에 "
        "대한 질문이나 조언도 포함한다.\n"
        "- advise: 광고와 무관한 일반 질문·잡담.\n"
        "광고 운영·성과·정책에 관한 것이면 manage, 광고와 무관하면 advise."
    )
    history = "\n".join(f"{m.role}: {m.content}" for m in req.messages[-6:])
    structured = llm.with_structured_output(_IntentPick)
    pick: _IntentPick = await structured.ainvoke(
        [("system", system), ("human", history)],
        config={
            "run_name": "assistant.classify_intent",
            "metadata": {"session_id": req.session_id},
        },
    )
    if pick.intent in registered or pick.intent == Intent.ADVISE:
        return pick.intent
    return Intent.ADVISE


async def classify_intent(req: SubagentRequest, registered: Sequence[Intent], llm=None) -> Intent:
    """등록된 의도 중 하나(또는 advise)로 분류. llm 있으면 계측 LLM, 없으면 키워드."""
    if llm is not None:
        try:
            return await _llm_classify(llm, req, registered)
        except Exception:  # noqa: BLE001 — 분류 실패는 키워드로 폴백(채팅 끊지 않음)
            pass
    return _keyword_classify(req.last_user_text, registered)
