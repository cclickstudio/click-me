# 페르소나 토론 파이프라인(조각 8~11) 전용 DTO — 반응분석·선발·배정·토론산출 계약
#
# contracts/schemas.py(도메인 공용)와 분리. 조각 8(반응분석)·9(KPI)·10(선발/배정/토론)·11(리포트)이
# 주고받는 내부 스키마를 한 곳에 모은다. 8·9·10-a·10-b는 결정론(LLM✗), 10-c·11만 LLM.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# AISAS 5단계 — 퍼널 순서 고정(이 순서로만 인접 비교).
AISAS_STAGES: list[str] = ["attention", "interest", "search", "action", "share"]

# 토론 입장 — 라운드별 stance. churn/dispersion 계산의 단위.
Stance = Literal["positive", "neutral", "negative"]


class FunnelStage(BaseModel):
    """AISAS 단계별 통과 현황 — 인원 카운트 기반(qa_passed 표본만)."""

    stage: str
    passed: int  # 이 단계 flag == true 인 인원 수
    pass_rate: float  # passed / total_n (총원 대비, 0~1)


class Bottleneck(BaseModel):
    """최대 이탈 구간 — 인접 단계 간 인원 감소가 가장 큰 곳(토론 주제 근거)."""

    from_stage: str
    to_stage: str
    dropped: int  # from.passed - to.passed (양수)
    drop_rate: float  # dropped / from.passed (직전 단계 대비 이탈률)


class GroupMembers(BaseModel):
    """소비자 그룹별 멤버(persona_id) — 조각 10-a 선발의 후보 풀.

    한 사람이 여러 그룹에 동시 소속 가능(겹침 허용). 배타 배정은 선발(10-a) 책임.
    """

    finishers: list[str] = Field(default_factory=list)  # 완주자: action == true
    undecided: list[str] = Field(default_factory=list)  # 미온 다수: interest and not action
    rejectors: list[str] = Field(default_factory=list)  # 거부자: rejected == true
    distrusters: list[str] = Field(default_factory=list)  # 불신자: emotion_tag == distrust
    early_drop: list[str] = Field(default_factory=list)  # 초기이탈: drop_stage == interest


class RejectionBreakdown(BaseModel):
    """거부·불신 분해 — 거부율 + 사유 + 불신 인원."""

    rejected_count: int
    rejection_rate: float  # rejected_count / total_n (인원 기반, 9의 가중 거부율과 별개)
    by_rejection_reason_tag: dict[str, int] = Field(default_factory=dict)
    distrust_count: int = 0  # emotion_tag == distrust 인원


class MessageReception(BaseModel):
    """조각 8 — 메시지 수신 갭(의도 메시지가 어떻게 받아들여졌나). 결정론 신호, 해석은 토론(LLM).

    의도(detected_message)는 그대로 토론에 넘기고, 여기선 '저항 표현(과장·식상·무관심)' 비율만
    결정론으로 센다. 점수가 정밀하진 않지만 "메시지가 안 먹혔다"는 신호와 인용은 잡는다.
    """

    intended: str | None = None  # 광고 의도 메시지(ad_analysis.detected_message)
    resistance_rate: float = 0.0  # 저항 표현 포함 반응 비율(0~1)
    resistance_terms: dict[str, int] = Field(default_factory=dict)  # 어떤 저항어가 몇 번
    resisted_quotes: list[str] = Field(default_factory=list)  # 저항 발언 샘플(토론 컨텍스트)


class ReactionAnalysis(BaseModel):
    """조각 8 산출 — 반응 데이터의 구조적 분석(결정론, LLM✗).

    funnel/bottleneck = 어디서 새는가, groups = 누가 어떤 무리인가(선발 후보 풀),
    breakdown/emotion_dist = 왜 새는가, message = 의도 메시지가 먹혔나. 10-a·11이 소비한다.
    """

    total_n: int  # qa_passed 표본 수
    funnel: list[FunnelStage]
    bottleneck: Bottleneck | None = None  # 표본 0 또는 이탈 없음이면 None
    by_drop_stage: dict[str, int] = Field(default_factory=dict)
    by_drop_reason_tag: dict[str, int] = Field(default_factory=dict)
    emotion_dist: dict[str, int] = Field(default_factory=dict)
    rejection: RejectionBreakdown
    groups: GroupMembers
    message: MessageReception | None = None  # 메시지 수신 갭(ad_analysis 있을 때만)


class SelectedParticipant(BaseModel):
    """조각 10-a 선발/합성 1명 — 슬롯·역할·입장점수.

    slot 1~4=전문가(도메인2·마케팅2, 합성), 5=피벗, 6=비판자(실제 반응자에서 선발).
    """

    persona_id: str
    slot: int  # 1도메인1 2도메인2 3마케팅1 4마케팅2 5피벗 6비판자
    role: str  # 한글 역할 라벨
    stance_score: float  # 비판자 선정 전용 입장 점수(전문가는 0.0)
    is_fallback: bool = False  # 일반인 슬롯 후보 없어 보충됐는지
    is_expert: bool = False  # 합성 전문가(실제 반응 없음 → 분석결과에 grounded)
    persona_profile: str | None = None  # 전문가만: 카테고리 주입된 프로필(일반인은 10-b에서 생성)


class SelectedPanel(BaseModel):
    """조각 10-a 산출 — 토론 패널(전문가 4 + 일반인). 합성·결정론 선발.

    personas(인구통계) 주입 시 타깃 적합 선발 — 반응 분포로 타깃층 역산 후 타깃 밖 후보 배제.
    """

    participants: list[SelectedParticipant]
    pivot_id: str | None = None  # 피벗 persona_id(일반인)
    critic_secured: bool = False  # 비판자(부정 입장) 최소 1명 확보 여부
    target_age_center: float | None = None  # 역산 타깃 나이 중심(좁은 타깃일 때만)
    target_genders: list[str] = Field(default_factory=list)  # 역산 타깃 성별(들)
    excluded_off_target: int = 0  # 타깃 밖이라 일반인 후보에서 배제된 인원
    broad_target: bool = False  # 전 연령형(타깃 불명확) — 배제 끄고 연령 다양성 선발


class DebateParticipant(BaseModel):
    """조각 10-b 산출 1명 — 선발/합성 결과 + 엔진·이름·프로필. 토론·DB·리포트 입력."""

    persona_id: str
    slot: int
    role: str
    stance_score: float
    is_fallback: bool = False
    is_expert: bool = False  # 전문가(분석결과 grounded) / 일반인(실제 반응 grounded)
    engine: str  # haiku / gpt / gemini (토론자). 역할 기반 라운드로빈(엔진 ⊥ 역할).
    persona_name: str  # 결정론 부여 이름(운영은 factory 이름 승계). 리포트 표시용.
    persona_profile: str  # 한 줄 프로필(전문가=카테고리 주입, 일반인=역할/인구 기반)
    tone: str = ""  # 일반인 말투(표현 스타일). 전문가는 빈 값 — 같은 모델 통일 시 표현 다양성용.


class AssignedPanel(BaseModel):
    """조각 10-b 산출 — 엔진·이름 배정 끝난 토론 패널. judge는 별도 고정(Sonnet 4.6)."""

    participants: list[DebateParticipant]
    pivot_id: str | None = None
    judge_engine: str = "sonnet"
    critic_secured: bool = False


class DebateTopic(BaseModel):
    """조각 9 산출 — 토론 주제(결정론). 8의 병목 + 9의 KPI + 캠페인 목표에서 파생.

    LLM 토론(10-c)의 시드 문장. 항상 실제 수치에 grounded(지어내지 않음).
    """

    headline: str  # 토론 제시 문장 ("신뢰 높은데 클릭 안 됨 — 무엇이 막나?")
    diagnosis: str  # 진단부(수치 근거)
    question: str  # 질문부(토론이 풀 것)
    primary_signal: (
        str  # 주신호 종류: rejection / trust_action_gap / early_attrition / mid_attrition
    )
    focus: dict[str, float | str | None] = Field(default_factory=dict)  # 근거 수치(병목·KPI)
    objective: str | None = None  # detected_objective(캠페인 목표)
    # ── 논제 후보(추가 토론 선택지)용 — 최초 토론(단일 주제)은 기본값 그대로 ──
    topic_id: str = ""  # 후보 식별자(추가 토론에서 사용자가 고른 논제 매칭용)
    ranking: int = 0  # 1~5 우선순위(0=미지정, 후보 정렬용)
    confidence: float = 0.0  # 신호 강도(0~1, 후보 정렬·표시용)


# ───────────────────────── 조각 10-c 토론 산출 ─────────────────────────


class Utterance(BaseModel):
    """라운드별 발언 1건 — 토론자가 내놓는 구조화 발화. DB(utterances)·리포트 인용 입력."""

    round: int
    phase: str  # 발산 / 반박 / 검증
    stance: Stance
    text: str  # 실제 발언(리포트 인용용)
    reason: str  # 왜 그렇게 말했나
    lever: str  # 이 사람을 움직이려면 뭘 바꿔야 하나


class ParticipantDebate(BaseModel):
    """토론자 1명의 전체 발언 — 배정 정보 + 라운드별 utterances."""

    persona_id: str
    persona_name: str
    persona_profile: str
    role: str
    engine: str
    utterances: list[Utterance] = Field(default_factory=list)


class RankedAction(BaseModel):
    """개선안 1건(우선순위) — 리포트 §4 핵심."""

    rank: int
    action: str
    expected_effect: str
    supporting_personas: list[str] = Field(default_factory=list)  # 뒷받침한 사람(이름)


class JudgeFinal(BaseModel):
    """Judge 최종 결론 — 진단 + 합의/이견 + 개선안 순위.

    headline·consensus·dissent·ranked_actions는 전문가용(정확한 용어 허용),
    plain_summary는 비전문가용(마케팅을 몰라도 바로 이해되는 쉬운 말 결론) — 둘 다 도출.
    """

    headline: str
    plain_summary: str = ""  # 비전문가용 — 전문 용어 없이 풀어쓴 결론(문제·원인·해법 일상어)
    consensus: list[str] = Field(default_factory=list)
    dissent: list[str] = Field(default_factory=list)
    ranked_actions: list[RankedAction] = Field(default_factory=list)


class DebateResult(BaseModel):
    """조각 10-c 산출 — 토론 전체(증거=participants + 결론=judge). 11 리포트·DB 입력.

    rounds_run/stop_reason 으로 유동 라운드(2~4) 추적. models 로 재현 정보 기록.
    """

    topic: str
    rounds_run: int
    stop_reason: str  # consensus / dissensus / max
    models: dict[str, object] = Field(default_factory=dict)  # judge·engines
    participants: list[ParticipantDebate] = Field(default_factory=list)
    round_summaries: dict[int, str] = Field(default_factory=dict)  # Judge 라운드 정리
    proposed_actions: list[str] = Field(default_factory=list)  # Judge 잠정 액션
    final: JudgeFinal | None = None


# ───────────────────────── 조각 11 리포트 ─────────────────────────


class ReportKpi(BaseModel):
    """리포트용 4대 KPI 묶음 — 9의 집계(SimulationAggregate)에서 그대로 가져온다."""

    click_intent_rate: float
    ci_low: float
    ci_high: float
    purchase_intent: float
    trust_avg: float
    rejection_rate: float
    variance_warning: bool
    effective_n: float


class ReportQuote(BaseModel):
    """리포트 '실제 소비자 목소리' 인용 1건 — 토론 발언 + 사람 이름."""

    persona_name: str
    role: str
    stance: Stance
    text: str


class SimulationReport(BaseModel):
    """조각 11 산출 — [KPI(9) + 분석(8) + 토론 결론·인용(10)] 조립(결정론, LLM✗).

    debate_available=False면 토론 미실행(엔진 미주입) — KPI·분석만 채우고 진단은 주제로 대체.
    """

    headline: str  # 진단 헤드라인(judge.final.headline 또는 topic.diagnosis) — 전문가용
    plain_summary: str = ""  # 비전문가용 쉬운 결론(judge.final.plain_summary). 토론 없으면 빈 값.
    topic: str
    kpi: ReportKpi
    funnel: list[FunnelStage]
    bottleneck: Bottleneck | None = None
    consumer_groups: dict[str, int] = Field(default_factory=dict)  # 그룹별 인원
    debate_available: bool = False
    rounds_run: int = 0
    stop_reason: str | None = None
    consensus: list[str] = Field(default_factory=list)
    dissent: list[str] = Field(default_factory=list)
    ranked_actions: list[RankedAction] = Field(default_factory=list)
    quotes: list[ReportQuote] = Field(default_factory=list)  # 참가자별 대표 발언
