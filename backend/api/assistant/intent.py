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
        "너는 광고 플랫폼 채팅의 의도 분류기다. 사용자의 마지막 메시지를 정확히 하나로 분류한다.\n"
        f"허용 라벨: {allowed}.\n\n"
        "분류 규칙 (우선순위 순):\n"
        "1. generate: '만들어', '만들어줘', '생성해', '제작해', '시안', '카피', '이미지 생성' 등 "
        "새 광고물·시안·카피·이미지를 만드는 요청.\n"
        "2. manage: 집행 중인 캠페인의 예산·성과·CTR/ROAS/CPC·이상 탐지·정책·벤치마크·타깃 등 "
        "운영 관련 질문 또는 조치(일시중지·예산증액 등) 요청.\n"
        "3. advise: 위 둘에 해당하지 않는 일반 질문이나 광고와 무관한 잡담.\n\n"
        "반드시 하나의 라벨만 출력한다. '만들어' 포함이면 generate 우선."
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
    """등록된 의도 중 하나(또는 advise)로 분류. llm 있으면 시맨틱 분류, 없으면 advise 기본값.

    키워드 폴백 제거 이유: 키워드 방식은 의미 분석이 불가능해 "프리퀀시 높으면?" 같은
    질문을 잘못 분류함. LLM API 키가 없으면 CLIO(advise)로 처리한다.
    """
    if llm is not None:
        try:
            result = await _llm_classify(llm, req, registered)
            print(f"[intent] {req.last_user_text[:40]!r} → {result}", flush=True)
            return result
        except Exception as e:  # noqa: BLE001 — 분류 실패는 advise 폴백(채팅 끊지 않음)
            print(f"[intent] 분류 실패 → ADVISE: {e!r}", flush=True)
    return Intent.ADVISE
