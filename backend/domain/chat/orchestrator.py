# 채팅 오케스트레이터 — 매니지/시뮬/생성 서브에이전트를 도구로 부르는 LLM 라우터
"""build_chat_orchestrator(settings) → ask(ChatTurn) -> ChatAnswer | None.

키+실모드면 classify_intent → route → 도메인 서브에이전트(매니지·시뮬·생성) 또는 advise(일반 조언).
아니면 키워드 폴백(매니지만 처리, 그 외 None → chat.py가 기존 CLIO(Gemini)로 답).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from core.assistant import AssistantRequest
from domain.chat import history
from domain.chat.loop_state import MAX_LOOP, get_loop_state
from domain.generator.assistant.agent import build_generator_agent
from domain.generator.assistant.tools import list_generations as _list_generations
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.simulation.assistant.agent import build_simulation_agent
from domain.simulation.assistant.tools import list_simulations as _list_simulations

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
# 정확도 핵심: 집행 전(simulation) vs 집행 후(management) 경계 + KPI 용어 정의는 항상 simulation.
_CLASSIFY_SYSTEM = (
    "너는 ClickMe 광고 플랫폼의 라우터다. 사용자 메시지를 정확히 하나의 도메인으로 분류한다.\n\n"
    "[도메인 정의]\n"
    "- simulation: 집행 '전' 시뮬레이션. KPI(클릭 의향률·구매의도·신뢰도·거부율)의 의미·해석·"
    "방법론 질문, 시뮬 결과 해석, 반응 예측·시뮬 실행 요청.\n"
    "- management: 집행 '후' 실측 성과·운영. 집행된 캠페인의 예산·소진·CTR/ROAS/CVR 실적·"
    "페이싱·증액/감액·일시중지 등.\n"
    "- generator: 광고 시안 생성·카피 전략·작성 원칙·시안 만들기 요청.\n"
    "- advise: 위 어디에도 안 맞는 일반 광고 전략·마케팅 아이디어·잡담.\n\n"
    "[판단 기준]\n"
    "- '집행 전 예측·KPI 의미'면 simulation, '집행 후 실측 성과'면 management. "
    "헷갈리면 실측 수치(이미 집행된 광고의 실적) 언급 여부로 가른다.\n"
    "- KPI 용어(클릭 의향률/구매의도/신뢰도/거부율)의 '정의·해석'은 항상 simulation.\n"
    "- 특정 과거 시뮬/생성의 결과를 묻거나 분석을 요청하면(예: '바나나우유 시뮬 반응 어땠어') "
    "목록이 아니라 그 도메인의 ask다.\n"
    "- 단순 인사·범위 밖 일반 질문은 advise.\n\n"
    "[action]\n"
    "- ask: 질문·조회·결과 분석.\n"
    "- run: 시뮬/생성을 실제 '돌려줘/실행/만들어줘'. 광고 카피·문구가 있으면 ad_content로, "
    "결과 ID가 있으면 context_id로 추출.\n"
    "- list: 내가 돌린/만든 것의 '목록'을 보려 할 때(예: '내가 돌린 시뮬 뭐 있어?').\n"
    "- select: 과거 항목 중 하나를 '골라' 개선·이어가려 할 때"
    "(예: '내가 돌린 시뮬 개선하고 싶어').\n\n"
    "[confidence] 분류 확신도 — 명확하면 high, 애매하면 medium, 거의 추측이면 low.\n\n"
    "[예시]\n"
    "'클릭 의향률이 무슨 뜻이야?' → simulation / ask\n"
    "'바나나우유 시뮬 반응 괜찮았어?' → simulation / ask\n"
    "'이 광고 반응 예측해줘 / 시뮬레이션 돌려줘' → simulation / run\n"
    "'내가 돌린 시뮬레이션 뭐 있어?' → simulation / list\n"
    "'내가 돌린 시뮬레이션 개선하고 싶어' → simulation / select\n"
    "'우리 캠페인 예산 소진율 알려줘' → management / ask\n"
    "'전환율 높이는 카피 전략 알려줘' → generator / ask\n"
    "'수분크림 광고 시안 만들어줘' → generator / run\n"
    "'내가 만든 시안 뭐 있어?' → generator / list\n"
    "'요즘 20대 마케팅 트렌드 뭐야?' → advise"
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

# 시뮬 실행 입력 추출 프롬프트 — 사용자 요청에서 시뮬 위젯 초기값 뽑기.
_SIM_EXTRACT_SYSTEM = (
    "사용자의 광고 시뮬레이션 요청에서 입력을 추출하라.\n"
    "- ad_title: 광고/제품 제목 (예: \"'여름세일'이라는 제목으로\" → 여름세일)\n"
    "- ad_content: 광고 카피·문구·설명\n"
    "- product_category: 상품 카테고리(있을 때만)\n"
    "- ad_objective: 광고 목표(있을 때만)\n"
    "명시되지 않은 항목은 빈 문자열로 두라(지어내지 말 것)."
)

# 시뮬 결과 요약 메시지에서 KPI 수치 추출 프롬프트 — sim_result_node에서 강약 판정에 쓴다.
_SIM_RESULT_EXTRACT_SYSTEM = (
    "시뮬레이션 결과 요약 메시지에서 KPI 수치를 추출하라.\n"
    "- purchase_intent: 구매의도(1~5점)\n"
    "- click_intent_rate: 클릭 의향률(0~1 비율, 18% → 0.18)\n"
    "- rejection_rate: 거부율(0~1 비율, 30% → 0.3)\n"
    "- product_category: 상품 카테고리(있을 때만, 예: 뷰티·식품)\n"
    "메시지에 없는 항목은 null로 두라."
)


def _copy_advice(reasons: list[str], brand: dict | None) -> str:
    """약한 이유에 맞춘 구체적 카피 개선 방향(T10) — '개선하세요' 대신 원인·방향 제시."""
    high_rej = any("거부율" in r for r in reasons)
    low_pi = any("구매의도" in r for r in reasons)
    cause: list[str] = []
    direction: list[str] = []
    if high_rej:
        cause.append(
            "거부율이 높을 때는 소구가 너무 직접적이거나 가격 언급이 과도한 경우가 많아요."
        )
        direction.append("가격·할인 전면 노출 대신 '경험·감성' 소구로 전환")
    if low_pi:
        cause.append("구매의도가 낮을 때는 혜택이 추상적이거나 차별점이 약한 경우가 많아요.")
        direction.append("구체적 사용 상황·전후 변화로 베네핏을 또렷하게")
    if brand and brand.get("target_audience"):
        direction.append(f"타깃({brand['target_audience']})이 공감할 상황 묘사 추가")
    parts = ["원인 분석:\n" + "\n".join(f"- {c}" for c in cause)] if cause else []
    if direction:
        parts.append("개선 방향:\n" + "\n".join(f"- {d}" for d in direction))
    return "\n\n".join(parts)


@dataclass
class ChatTurn:
    """채팅 한 턴 입력 — 질문 + 직전 대화 + 광고 맥락."""

    question: str
    history: list[tuple[str, str]] = field(
        default_factory=list
    )  # (role, content), role=user|assistant
    ad_id: str | None = None
    session_id: str | None = None  # 개선 루프 상태 키(턴 간 보존)
    project_id: str | None = None  # 목록 조회 스코프(현재 프로젝트)


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


# sim_result_node의 강약 판정 임계값 — 위젯이 보낸 시뮬 결과를 약함/충분으로 가른다.
_TARGET_PI = 3.5  # 목표 구매의도(미만이면 약함 — 개선 제안)
_HIGH_REJECTION = 0.3  # 거부율 임계값(이상이면 약함 — 개선 제안)


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

    from langchain_core.messages import (  # noqa: PLC0415 — 키 있을 때만
        AIMessage,
        HumanMessage,
        SystemMessage,
    )
    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415
    from pydantic import BaseModel  # noqa: PLC0415

    model_name = getattr(settings, "chat_orchestrator_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.2, api_key=api_key)
    # 분류는 결정론적으로(temperature 0) — 같은 질문이 매번 같은 도메인으로 가게 한다.
    classify_llm = ChatOpenAI(model=model_name, temperature=0, api_key=api_key)
    sim = build_simulation_agent(settings)  # 시뮬 서브에이전트(폴백/풀모드 자동)
    gen = build_generator_agent(settings)  # 생성 서브에이전트(폴백/풀모드 자동)

    # classify_intent 출력 스키마 — 도메인 분류 + 결과 식별자 추출.
    # sim_result/gen_result는 LLM 분류 대상 아님(위젯의 [시뮬결과]/[생성결과] 접두사로 결정론 분기).
    class _Intent(BaseModel):
        intent: Literal["management", "simulation", "generator", "advise"]
        action: Literal["ask", "run", "list", "select"] = "ask"
        confidence: Literal["high", "medium", "low"] = "high"  # 분류 확신도(라우팅 로그용)
        context_id: str | None = None
        ad_content: str | None = None

    # 시뮬 결과 요약에서 강약 판정용 KPI 추출 스키마.
    class _SimResult(BaseModel):
        purchase_intent: float | None = None  # 1~5
        click_intent_rate: float | None = None  # 0~1
        rejection_rate: float | None = None  # 0~1
        product_category: str | None = None  # KOBACO 벤치마크 대조용(있을 때만)

    # 생성 실행 입력 추출 스키마 — generator_node에서 question으로부터 채운다.
    class _GenInput(BaseModel):
        product_name: str = ""
        product_description: str = ""
        target_audience: str = ""
        campaign_objective: str = "conversion"

    # 시뮬 실행 입력 추출 스키마 — simulation_node에서 위젯 초기값으로 채운다.
    class _SimInput(BaseModel):
        ad_title: str = ""
        ad_content: str = ""
        product_category: str = ""
        ad_objective: str = ""

    # 브랜드 프로파일 추출 스키마 — 사용자 발화에서 브랜드 설정 부분 업데이트.
    class _BrandExtract(BaseModel):
        brand_name: str = ""
        tone: str = ""
        target_audience: str = ""
        product_category: str = ""
        keywords: list[str] = []

    classifier = classify_llm.with_structured_output(_Intent)

    # ── 숏텀 메모리 — session_id 키로 윈도우 버퍼(k=6) 캐시 ──
    # LangChain 1.x에서 ConversationBufferWindowMemory가 제거돼, 같은 의미(최근 k턴 윈도잉)를
    # langchain_core 메시지로 직접 구현. 서버 프로세스 메모리에만 보관(재시작 시 초기화).
    class _WindowMemory:
        """최근 k턴(2k 메시지)만 유지하는 단순 버퍼 — save_context/load 의미 보존."""

        def __init__(self, k: int = 6) -> None:
            self.k = k
            self.messages: list = []  # HumanMessage | AIMessage

        def seed(self, history: list[tuple[str, str]]) -> None:
            for role, content in history:
                self.messages.append(
                    AIMessage(content=content)
                    if role == "assistant"
                    else HumanMessage(content=content)
                )
            self._trim()

        def save_context(self, user_input: str, output: str) -> None:
            self.messages.append(HumanMessage(content=user_input))
            self.messages.append(AIMessage(content=output))
            self._trim()

        def _trim(self) -> None:
            limit = self.k * 2
            if len(self.messages) > limit:
                self.messages = self.messages[-limit:]

        def load(self) -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for m in self.messages:
                role = "assistant" if isinstance(m, AIMessage) else "user"
                out.append((role, m.content if isinstance(m.content, str) else str(m.content)))
            return out

    _short_term: dict[str, _WindowMemory] = {}

    def _get_memory(session_id: str | None, seed: list[tuple[str, str]]) -> _WindowMemory:
        key = session_id or "__ephemeral__"
        mem = _short_term.get(key)
        if mem is None:
            mem = _WindowMemory(k=6)
            # 새 메모리(서버 재시작/첫 턴)면 클라이언트가 보낸 내역으로 시드.
            mem.seed(seed)
            _short_term[key] = mem
        return mem

    # 그래프 상태 — 메시지 누적이 아니라 분류→답변 1패스. 노드엔 어노테이트하지 않는다.
    class _State(TypedDict, total=False):
        question: str
        session_id: str | None
        project_id: str | None
        history: list[tuple[str, str]]
        ltm: list[dict]
        brand: dict | None
        intent: str
        action: str
        context_id: str | None
        ad_content: str | None
        answer: str
        meta: dict

    async def classify(state) -> dict:
        q = (state.get("question") or "").strip()
        # 위젯이 보낸 결과 보고는 LLM 분류 없이 결정론 분기(일반 질문이 결과노드로 새는 것 방지).
        if q.startswith("[시뮬결과]"):
            return {"intent": "sim_result", "action": "ask", "confidence": "high"}
        if q.startswith("[생성결과]"):
            return {"intent": "gen_result", "action": "ask", "confidence": "high"}
        # 직전 대화를 맥락으로 덧붙여 후속 질문(예: "그거 확실해?")도 제대로 분류한다.
        msgs = [SystemMessage(content=_CLASSIFY_SYSTEM)]
        for role, content in (state.get("history") or [])[-4:]:
            msgs.append(HumanMessage(content=f"({role}) {content}"))
        msgs.append(HumanMessage(content=q))
        res = await classifier.ainvoke(msgs)
        return {
            "intent": res.intent,
            "action": res.action,
            "confidence": res.confidence,
            "context_id": res.context_id,
            "ad_content": res.ad_content,
        }

    async def management_node(state) -> dict:
        res = await mgmt(
            AskRequest(question=state["question"], campaign_id=state.get("context_id"))
        )
        return {"answer": _mgmt_answer(res), "meta": _mgmt_meta(res)}

    async def simulation_node(state) -> dict:
        action = state.get("action")
        if action in ("list", "select"):
            # 목록 위젯 — 읽기용(보기) / 선택용(개선 이어가기).
            items = await _list_simulations(state.get("project_id") or "", limit=10)
            mode = "select" if action == "select" else "read"
            label = "시뮬레이션 선택" if mode == "select" else "내 시뮬레이션"
            answer = (
                "개선할 시뮬레이션을 골라주세요."
                if mode == "select"
                else ("최근 시뮬레이션 목록이에요." if items else "아직 돌린 시뮬레이션이 없어요.")
            )
            return {
                "answer": answer,
                "meta": {
                    "source": "simulation",
                    "label": label,
                    "widget": {"type": "sim_list", "mode": mode, "data": {"items": items}},
                },
            }
        if action == "run":
            # 채팅에 이미 준 값(제목·카피·카테고리·목표)을 추출해 위젯 초기값으로 채운다.
            extractor = llm.with_structured_output(_SimInput)
            si = await extractor.ainvoke(
                [
                    SystemMessage(content=_SIM_EXTRACT_SYSTEM),
                    HumanMessage(content=state["question"]),
                ]
            )
            sim_data = {
                "ad_title": si.ad_title,
                "ad_content": si.ad_content or (state.get("ad_content") or ""),
                "product_category": si.product_category,
                "ad_objective": si.ad_objective,
            }
            # 롱텀 메모리 — 시뮬 실행 입력을 프로젝트 단위로 누적(다음 대화 컨텍스트).
            await history.save_long_term_memory(state.get("project_id"), "sim_input", sim_data)
            # 위젯 방식 — 백엔드 직접 실행 대신 입력 위젯을 띄운다(프론트가 기존 라우터로 실행).
            return {
                "answer": "시뮬레이션을 돌릴게요. 아래에서 광고 정보를 확인·수정하고 실행하세요.",
                "meta": {
                    "source": "simulation",
                    "label": "시뮬레이션",
                    "widget": {"type": "sim_form", "data": sim_data},
                },
            }
        res = await sim(
            AssistantRequest(
                question=state["question"],
                context_id=state.get("context_id"),
                project_id=state.get("project_id"),
                history=state.get("history") or [],
            )
        )
        return {
            "answer": res.answer,
            "meta": _assistant_meta(res, "simulation", "시뮬레이션 어시스턴트"),
        }

    async def generator_node(state) -> dict:
        action = state.get("action")
        if action in ("list", "select"):
            items = await _list_generations(state.get("project_id") or "", limit=10)
            mode = "select" if action == "select" else "read"
            label = "생성 선택" if mode == "select" else "내 광고 생성"
            answer = (
                "이어서 작업할 생성을 골라주세요."
                if mode == "select"
                else ("최근 광고 생성 목록이에요." if items else "아직 만든 시안이 없어요.")
            )
            return {
                "answer": answer,
                "meta": {
                    "source": "generator",
                    "label": label,
                    "widget": {"type": "gen_list", "mode": mode, "data": {"items": items}},
                },
            }
        if action == "run":
            extractor = llm.with_structured_output(_GenInput)
            gi = await extractor.ainvoke(
                [
                    SystemMessage(content=_GEN_EXTRACT_SYSTEM),
                    HumanMessage(content=state["question"]),
                ]
            )
            gen_data = {
                "product_name": gi.product_name,
                "product_description": gi.product_description,
                "target_audience": gi.target_audience,
                "campaign_objective": gi.campaign_objective,
            }
            # 롱텀 메모리 — 생성 실행 입력을 프로젝트 단위로 누적(다음 대화 컨텍스트).
            await history.save_long_term_memory(state.get("project_id"), "gen_input", gen_data)
            # 위젯 방식 — 추출한 값을 초기값으로 입력 위젯을 띄운다(프론트가 기존 라우터로 실행).
            return {
                "answer": "광고 시안을 만들게요. 아래에서 생성 정보를 확인·수정하고 실행하세요.",
                "meta": {
                    "source": "generator",
                    "label": "생성",
                    "widget": {"type": "gen_form", "data": gen_data},
                },
            }
        res = await gen(
            AssistantRequest(
                question=state["question"],
                context_id=state.get("context_id"),
                project_id=state.get("project_id"),
                history=state.get("history") or [],
            )
        )
        return {"answer": res.answer, "meta": _assistant_meta(res, "generator", "생성 어시스턴트")}

    async def sim_result_node(state) -> dict:
        # 위젯이 보낸 시뮬 결과 요약 → 수치 추출 후 강약 판정. 실행은 안 하고 제안만.
        ext = llm.with_structured_output(_SimResult)
        m = await ext.ainvoke(
            [
                SystemMessage(content=_SIM_RESULT_EXTRACT_SYSTEM),
                HumanMessage(content=state["question"]),
            ]
        )
        reasons = []
        if m.purchase_intent is not None and m.purchase_intent < _TARGET_PI:
            reasons.append(f"구매의도 {m.purchase_intent:.1f}/5 (목표 {_TARGET_PI})")
        if m.rejection_rate is not None and m.rejection_rate >= _HIGH_REJECTION:
            reasons.append(f"거부율 {m.rejection_rate * 100:.0f}%")
        # KOBACO 벤치마크 — 카테고리가 있으면 업계 평균과 자동 대조(T08).
        bench_line = ""
        if m.product_category:
            from domain.simulation.assistant.tools import (  # noqa: PLC0415
                fetch_kobaco_benchmark,
            )

            b = fetch_kobaco_benchmark(m.product_category)
            if b.get("found") and m.purchase_intent is not None:
                diff = m.purchase_intent - b["purchase_intent"]
                sign = "+" if diff >= 0 else ""
                bench_line = (
                    f"\n\n{b['category']} 카테고리 평균(구매의도 {b['purchase_intent']}) "
                    f"대비 {sign}{diff:.1f}."
                )
        # 개선 루프 — 약하면 왕복 카운트 확인 후 HITL approval 제안, 충분하면 종료.
        loop = get_loop_state(state.get("session_id"))
        brand = state.get("brand")
        if reasons:
            loop.phase = "sim_done"
            loop.weak_reasons = reasons
            if loop.loop_count < MAX_LOOP:
                advice = _copy_advice(reasons, brand)
                answer = (
                    f"결과가 다소 약해요 — {', '.join(reasons)}.{bench_line}\n\n"
                    f"{advice}\n\n"
                    f"개선 시안을 만들어볼까요? (왕복 {loop.loop_count + 1}/{MAX_LOOP})"
                ).replace("\n\n\n\n", "\n\n")
                meta = {
                    "source": "simulation",
                    "label": "결과 분석 · 개선 제안",
                    "engine": f"OpenAI · {model_name}",
                    "suggest": "generator",
                    "approval": {
                        "action": "run_generator",
                        "label": "개선 시안 만들기",
                        "reasons": reasons,
                    },
                }
            else:
                loop.phase = "finished"
                answer = (
                    f"개선 왕복을 {MAX_LOOP}회 모두 시도했어요 — "
                    f"마지막 결과는 {', '.join(reasons)}.\n\n"
                    "여기서 루프를 마무리할게요. 카피 방향을 직접 다듬어 다시 시도해보셔도 좋아요."
                )
                meta = {
                    "source": "simulation",
                    "label": "개선 루프 종료",
                    "engine": f"OpenAI · {model_name}",
                }
        else:
            loop.phase = "finished"
            answer = (
                "목표 도달이에요(구매의도·거부율 충족). 이대로 집행을 검토해도 좋아요." + bench_line
            )
            meta = {
                "source": "simulation",
                "label": "결과 분석 · 목표 도달",
                "engine": f"OpenAI · {model_name}",
            }
        return {"answer": answer, "meta": meta}

    async def gen_result_node(state) -> dict:
        # 위젯이 보낸 생성 결과 요약 → 새 시안으로 재시뮬 제안. 실행은 안 하고 제안만.
        loop = get_loop_state(state.get("session_id"))
        loop.phase = "gen_done"
        meta = {
            "source": "generator",
            "label": "결과 분석 · 재시뮬 제안",
            "engine": f"OpenAI · {model_name}",
            "suggest": "simulation",
        }
        # 개선 루프 중이면(왕복 여력 있음) 재시뮬 approval을 함께 제안.
        if loop.loop_count < MAX_LOOP:
            meta["approval"] = {
                "action": "rerun_simulation",
                "label": "새 시안으로 재시뮬",
                "reasons": loop.weak_reasons,
            }
        return {
            "answer": ("새 시안이 준비됐네요. 새 시안으로 반응을 다시 예측해볼까요?"),
            "meta": meta,
        }

    async def advise_node(state) -> dict:
        # 롱텀 메모리 + 브랜드 프로파일을 시스템 프롬프트 앞에 주입(프로젝트 맥락).
        preamble = _format_brand(state.get("brand")) + _format_ltm(state.get("ltm") or [])
        msgs = [SystemMessage(content=preamble + _ADVISE_SYSTEM)]
        for role, content in (state.get("history") or [])[-6:]:
            msgs.append(
                AIMessage(content=content) if role == "assistant" else HumanMessage(content=content)
            )
        msgs.append(HumanMessage(content=state["question"]))
        resp = await llm.ainvoke(msgs)
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
    g.add_node("sim_result", sim_result_node)
    g.add_node("gen_result", gen_result_node)
    g.add_node("advise", advise_node)
    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        route,
        {
            "management": "management",
            "simulation": "simulation",
            "generator": "generator",
            "sim_result": "sim_result",
            "gen_result": "gen_result",
            "advise": "advise",
        },
    )
    for _node in (
        "management",
        "simulation",
        "generator",
        "sim_result",
        "gen_result",
        "advise",
    ):
        g.add_edge(_node, END)
    graph = g.compile()

    async def _ask_full(turn: ChatTurn) -> ChatAnswer:
        sid = turn.session_id
        # 숏텀 메모리에서 윈도우 내역을 꺼내 노드에 전달(raw 전체 history 대신 최근 6턴).
        q = (turn.question or "").strip()
        # /비교 명령어 — 시뮬 목록을 다중 선택(compare) 모드로 띄운다(T14).
        if q.replace(" ", "").startswith("/비교"):
            items = await _list_simulations(turn.project_id or "", limit=10)
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
        _tpl_meta = {"source": "simulation", "label": "템플릿", "engine": f"OpenAI · {model_name}"}
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
        # 배치 시뮬 요청은 그래프 없이 바로 입력 위젯을 띄운다(광고 2개 비교).
        if _is_batch_sim(q):
            return ChatAnswer(
                answer="여러 광고를 한 번에 비교할게요. 아래에 광고 2개를 입력하고 실행하세요.",
                meta={
                    "source": "simulation",
                    "label": "배치 시뮬",
                    "widget": {"type": "batch_sim_form"},
                },
            )
        # 브랜드 설정 조회 요청은 그래프 없이 바로 현재 프로파일을 출력.
        if _is_brand_show(q):
            brand = await history.get_brand_profile(turn.project_id)
            return ChatAnswer(
                answer=_brand_show_text(brand),
                meta={
                    "source": "orchestrator",
                    "label": "브랜드 설정",
                    "engine": f"OpenAI · {model_name}",
                },
            )
        # 브랜드 단서가 있으면 발화에서 설정을 추출해 자동 업데이트(부분 upsert).
        if turn.project_id and _has_brand_cue(q):
            try:
                be = await llm.with_structured_output(_BrandExtract).ainvoke(
                    [SystemMessage(content=_BRAND_EXTRACT_SYSTEM), HumanMessage(content=q)]
                )
                await history.upsert_brand_profile(turn.project_id, be.model_dump())
            except Exception as exc:  # noqa: BLE001 — 추출 실패가 대화를 막지 않게
                print(f"[chat] brand extract error: {exc!r}")
        mem = _get_memory(sid, turn.history or [])
        windowed = mem.load()
        # 진입 시 프로젝트 롱텀 메모리·브랜드 프로파일 조회 → 노드에서 시스템 프롬프트 앞 주입.
        ltm = await history.get_long_term_memory(turn.project_id, limit=3)
        brand = await history.get_brand_profile(turn.project_id)
        # 1턴 = 1 트레이스 루트(classify → route → 서브에이전트).
        final = await graph.ainvoke(
            {
                "question": turn.question,
                "session_id": sid,
                "project_id": turn.project_id,
                "history": windowed,
                "ltm": ltm,
                "brand": brand,
            },
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
        # 라우팅 정확도 로그(T20) — classify 결과를 meta에 실어 chat_messages.meta로 영속.
        if final.get("intent"):
            meta = {
                **meta,
                "routing": {
                    "intent": final.get("intent"),
                    "action": final.get("action"),
                    "confidence": final.get("confidence", "high"),
                },
            }
        answer = final.get("answer", "")
        # 이번 턴을 메모리에 적재 — 다음 턴의 윈도우에 반영.
        mem.save_context(turn.question, answer)
        return ChatAnswer(answer=answer, meta=meta)

    return _ask_full
