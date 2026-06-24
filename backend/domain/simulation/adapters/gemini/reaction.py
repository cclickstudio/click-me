# 4-b 반응 어댑터 — 페르소나가 광고에 '한 사람처럼' 반응(§3.5 구조화 JSON 강제, 비동기).
#
# 다양성 보존 위해 temperature 높게(동질화 방지). 숫자(집계)는 코드, 반응 '문장'만 LLM.
from __future__ import annotations

import random
from datetime import datetime

from domain.simulation.adapters.gemini._common import (
    _DEFAULT_MODEL,
    _agen_json,
    _enum_values,
    _new_client,
)
from domain.simulation.contracts.enums import (
    AisasStage,
    DropReasonTag,
    EmotionTag,
    RejectionReasonTag,
)
from domain.simulation.contracts.schemas import AdInterpretation, Aisas, PersonaReaction
from domain.simulation.tools.reachability import pick_social_exposure


def _pick_exposure(persona, rng: random.Random) -> str | None:
    # Meta 전용 — 노출맥락은 항상 소셜피드. 비소셜(TV·신문 등)로는 절대 폴백하지 않는다(모순 차단).
    cands = persona.media_behavior.get("exposure_candidates") or []
    e = pick_social_exposure(cands, rng)
    if e is None:
        # 소셜 후보가 없으면(구버전 패널 등) 일반 소셜피드 기본값 — TV 등 비소셜 금지.
        return "저녁·집·스마트폰/휴대폰·SNS"
    return f"{e['timeband']}·{e['place']}·{e['medium']}·{e['activity']}"


def _ad_feature_lines(ad: AdInterpretation, income: str) -> str:
    """광고 특성을 반응 힌트 줄로 — 가격은 월소득과 나란히 둬 적합도를 LLM이 판단(공식 없음)."""
    f = ad.ad_features
    lines: list[str] = []
    if f.price_mentioned and (f.original_price or f.discounted_price):
        if f.discounted_price and f.original_price:
            price = f"정가 {f.original_price:,}원 → 할인가 {f.discounted_price:,}원"
        else:
            price = f"{(f.discounted_price or f.original_price):,}원"
        lines.append(f"- 가격: {price} (내 월소득 {income} 기준으로 비싼지/적당한지 판단)")
    if f.brand_mentioned:
        lines.append("- 브랜드 언급: 있음")
    if f.social_proof_strength and f.social_proof_strength != "none":
        lines.append(f"- 사회적 증거(후기·인기): {f.social_proof_strength}")
    return ("\n" + "\n".join(lines)) if lines else ""


# 전 연령형(타깃 불명확) 포괄어 — 이게 들어간 detected_target은 '연령 단서 없음'으로 본다.
# tools/debate/selector.py 에 유사 리스트가 있으나 동료(분석·토론) 소유라 import 않고 로컬 복제.
_BROAD_TARGET_TERMS = (
    "전 연령",
    "전연령",
    "일반 대중",
    "일반 소비자",
    "누구나",
    "남녀노소",
    "온 가족",
    "전 국민",
    "모든",
    "전반",
)


def _has_age_or_brand_cue(ad: AdInterpretation) -> bool:
    """광고에 실제 연령·브랜드 단서가 있는가 — 있을 때만 세대 친숙도 프레임을 주입한다.

    단서 없는(연령 무관·무명) 광고에 '내 세대 vs 젊은 세대' 틀을 무조건 심으면 40+가
    엉뚱하게 '젊은 애들용'으로 수렴 → 단서 게이팅으로 과증폭을 막는다.
    """
    sa = ad.structured_analysis or {}
    be = sa.get("brand_era")
    if isinstance(be, dict) and be.get("identified"):
        return True
    aw = sa.get("awareness_by_age")
    if isinstance(aw, dict) and aw:
        return True
    target = (ad.detected_target or "").strip()
    return bool(target) and not any(t in target for t in _BROAD_TARGET_TERMS)


def _generation_lines(age: int, ad: AdInterpretation) -> str:
    """나이 → 형성기(reminiscence bump 15~25세) 문맥 + 말투(항상) + 세대 친숙도(조건부) (Tier 1).

    말투·형성기 문맥은 전 페르소나에 유익하므로 항상 출력. '내 세대 vs 젊은 세대 친숙도/낯섦'
    프레임만 _has_age_or_brand_cue(ad) 일 때 주입 — 다양성은 데이터(나이)에서, 과증폭은 게이팅으로.
    (PERSONA_COHORT_KNOWLEDGE_STRATEGY Tier 1)
    """
    birth_year = datetime.now().year - int(age)
    form_start, form_end = birth_year + 15, birth_year + 25
    familiarity = (
        "- 그 시기에 익숙했던 브랜드·캐릭터·트렌드와, "
        "요즘 젊은 세대가 쓰는 것에 대한 친숙도는 다릅니다. "
        "이 광고의 브랜드·소재가 '내 세대에 익숙한지'를 내 나이에 비추어 판단하고, "
        "잘 모르는 브랜드면 아는 척하지 말고 '낯섦'을 반영해 반응하세요.\n"
        if _has_age_or_brand_cue(ad)
        else ""
    )
    return (
        "\n[내 세대]\n"
        f"- 브랜드·문화 취향이 형성된 시기는 대략 {form_start}~{form_end}년입니다.\n"
        f"{familiarity}"
        "- utterance(반응 문장)는 내 나이대가 실제로 쓰는 말투·어휘·어미로 말하세요. "
        "젊으면 젊은 대로, 나이 들면 그 세대의 자연스러운 어투로 — 단 과장된 유행어·밈 남발은 금지."
    )


def _brand_era_lines(ad: AdInterpretation) -> str:
    """공유 브랜드 시대성(structured_analysis.brand_era §4.4 Tier 2)을 반응 힌트 줄로.

    전원 동일한 '사실'(전성기·세대 친숙도)만 주입 — 친숙/낯섦 판단은 페르소나 나이(형성기)가 한다.
    식별 실패(identified=false)·필드 없으면 빈 문자열 → 기존 동작 그대로.
    (PERSONA_COHORT_KNOWLEDGE_STRATEGY Tier 2)
    """
    be = ad.structured_analysis.get("brand_era") if ad.structured_analysis else None
    if not isinstance(be, dict) or not be.get("identified"):
        return ""
    bits = [str(be[k]) for k in ("era", "note") if be.get(k)]
    if not bits:
        return ""
    return (
        "\n- 브랜드 시대성(전원 공유 사실): " + " — ".join(bits) + " (친숙/낯섦은 내 형성기로 판단)"
    )


def _visual_lines(ad: AdInterpretation) -> str:
    """공유 시각 인벤토리(structured_analysis.visual_elements §4-a)를 반응 힌트 줄로.

    전원 동일(공유 해석) — 같은 비주얼을 보여주되, 무엇을 더 보는지는 페르소나 프로필이 판단.
    visual_elements 없으면(mock 구버전·텍스트 광고) 빈 문자열 → 기존 동작 그대로.
    """
    ve = ad.structured_analysis.get("visual_elements") if ad.structured_analysis else None
    if not isinstance(ve, dict):
        return ""
    lines: list[str] = []
    if ve.get("primary_subject"):
        lines.append(f"- 핵심 피사체: {ve['primary_subject']}")
    if ve.get("first_impression"):
        lines.append(f"- 첫눈에 띄는 것: {ve['first_impression']}")
    elements = ve.get("elements")
    if isinstance(elements, list) and elements:
        lines.append(f"- 주요 시각요소: {', '.join(str(e) for e in elements)}")
    if ve.get("color_tone"):
        lines.append(f"- 색감·톤: {ve['color_tone']}")
    return ("\n[광고 비주얼]\n" + "\n".join(lines)) if lines else ""


def _awareness_band(age: int) -> str:
    """나이 → 브랜드 인지율 연령밴드(10-19~60-69). 60+는 60-69 칸을 읽는다."""
    if age < 20:
        return "10-19"
    if age >= 60:
        return "60-69"
    return f"{age // 10 * 10}-{age // 10 * 10 + 9}"


def _awareness_lines(ad: AdInterpretation, age: int) -> str:
    """Tier 3 브랜드 인지율(structured_analysis.awareness_by_age)을 내 연령대 기준 반응 힌트 줄로.

    공유 1회 룩업값을 페르소나는 자기 연령대 칸만 읽는다(다양성=나이, 사실=공유). 없으면 "".
    """
    sa = ad.structured_analysis or {}
    aw = sa.get("awareness_by_age")
    if not isinstance(aw, dict):
        return ""
    band = _awareness_band(age)
    rate = aw.get(band)
    if rate is None:
        return ""
    brand = sa.get("awareness_brand") or "이 광고 브랜드"
    pct = round(float(rate) * 100)
    return (
        f"\n[브랜드 인지도]\n- {brand}는 내 또래({band}) 인지도 약 {pct}%. "
        "낮으면 낯섦, 높으면 익숙함을 반응에 반영(아는 척·모르는 척 금지)."
    )


def _social_values_lines(persona) -> str:
    """단계3 한국 특화 심리(체면·동조·눈치)를 반응 힌트 줄로. 비면 ""(현 동작 보존)."""
    sv = getattr(persona, "social_values_deep", None) or {}
    if not sv:
        return ""
    parts = ", ".join(f"{k} {round(float(v) * 100)}%" for k, v in sv.items())
    return f"\n[내 성향(한국 특화)]\n- {parts} (높을수록 강함 — 반응·말투에 반영)"


_OCEAN_KO = {
    "openness": "개방성",
    "conscientiousness": "성실성",
    "extraversion": "외향성",
    "agreeableness": "친화성",
    "neuroticism": "신경증",
}
_OCEAN_ORDER = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def _ocean_level(z: float) -> str:
    """표준화 factor score → 정성 수준(LLM이 raw 숫자보다 잘 연기)."""
    if z >= 1.0:
        return "매우 높음"
    if z >= 0.4:
        return "높음"
    if z > -0.4:
        return "보통"
    if z > -1.0:
        return "낮음"
    return "매우 낮음"


def _ocean_descriptors(ocean: dict[str, float]) -> str:
    """OCEAN 5차원 z-score를 '개방성 높음·외향성 매우 높음…' 정성 묘사로. 비면 '(미상)'."""
    parts = [f"{_OCEAN_KO[d]} {_ocean_level(float(ocean[d]))}" for d in _OCEAN_ORDER if d in ocean]
    return ", ".join(parts) or "(미상)"


def _media_line(mb: dict) -> str:
    """주 이용 미디어 + 하루 이용 강도(헤비/보통/라이트)를 한 줄로 — 미디어 친숙도 단서."""
    primary = mb.get("primary_medium", "?")
    mins = mb.get("daily_media_minutes")
    if isinstance(mins, (int, float)) and mins > 0:
        level = "헤비" if mins >= 360 else ("라이트" if mins < 120 else "보통")
        return f"- 주 이용 미디어: {primary} (하루 약 {int(mins)}분, {level} 이용자)"
    return f"- 주 이용 미디어: {primary}"


def _trust_anchor_line() -> str:
    """trust(신뢰도) 1~5 척도 앵커 — 정의 없이 LLM 통념에 맡기던 걸 사람 관점 기준으로 고정."""
    return (
        "trust(신뢰도)는 1=과장·허위 같아 전혀 못 믿겠다, 3=반신반의, "
        "5=내용이 사실 같고 충분히 믿을 만하다 기준으로 고른다. "
    )


def build_reaction_prompt(persona, ad: AdInterpretation, exposure: str | None) -> str:
    """4-b 반응 프롬프트(프로바이더 무관) — Gemini·OpenAI 어댑터가 공유한다."""
    income = persona.socioeconomic.get("income_bracket", "?")
    edu = persona.socioeconomic.get("education", "?")
    values = [k for k, v in persona.consumption_values.items() if v]
    return (
        "당신은 아래 한국 소비자 '본인'입니다. 지금 인스타그램·페이스북(메타) 피드를 "
        "넘겨보다가 아래 광고를 마주쳤습니다. 이 사람의 성격·형편·미디어 습관에 충실하게, "
        "광고에 솔직하게 반응하세요. 피드 광고라 관심이 없으면 손가락으로 즉시 넘길 수 "
        "있습니다. 교과서적 정답이 아니라 이 사람의 실제 반응을.\n\n"
        f"[나]\n- {persona.age}세 {persona.gender}, {persona.region}\n"
        f"- 학력 {edu}, 월소득 {income}\n"
        f"- 성격(OCEAN): {_ocean_descriptors(persona.ocean)}\n"
        f"{_media_line(persona.media_behavior)}\n"
        f"- 중시 소비가치: {values}\n"
        f"- 서사: {persona.profile_narrative or '(없음)'}\n"
        f"- 지금 노출 맥락: {exposure or '일반'}"
        f"{_social_values_lines(persona)}"
        f"{_generation_lines(persona.age, ad)}\n\n"
        f"[광고]\n- 업종: {ad.detected_industry} / 목적: {ad.detected_objective}\n"
        f"- 메시지: {ad.detected_message}"
        f"{_ad_feature_lines(ad, income)}"
        f"{_brand_era_lines(ad)}"
        f"{_visual_lines(ad)}{_awareness_lines(ad, persona.age)}\n\n"
        "[출력 — 아래 JSON만, 설명·코드펜스 없이]\n"
        "{\n"
        '  "aisas": {"attention": bool, "interest": bool, "search": bool, '
        '"action": bool, "share": bool},\n'
        f'  "drop_stage": null 또는 [{_enum_values(AisasStage)}] 중 이탈 단계,\n'
        f'  "drop_reason_tag": null 또는 [{_enum_values(DropReasonTag)}] 중 하나,\n'
        '  "purchase_intent": 1~5 정수, "trust": 1~5 정수, "rejected": bool,\n'
        f'  "rejection_reason_tag": null 또는 [{_enum_values(RejectionReasonTag)}] 중 하나,\n'
        f'  "emotion_tag": [{_enum_values(EmotionTag)}] 중 하나,\n'
        '  "perceived_message": "내가 이해한 메시지", "perceived_target": "내가 느낀 타깃",\n'
        '  "brand_recognized": bool,  // 이 광고가 어느 브랜드/제품 광고인지 명확히 알겠는가\n'
        '  "perceived_brand": "내가 인식한 브랜드/제품명(모르겠으면 null)",\n'
        '  "noticed_first": "이 광고에서 내 성격·중시 소비가치상 '
        '가장 먼저 눈에 들어온 요소 한 가지",\n'
        '  "utterance": "한 문장 솔직한 반응"\n'
        "}\n"
        "주의: AISAS는 깔때기 — action=true면 attention·interest도 true여야 한다. "
        "brand_recognized는 광고를 보고 '무슨 브랜드/제품 광고인지' 분명히 떠오를 때만 true. "
        f"{_trust_anchor_line()}"
        "태그는 반드시 제시된 값에서만 고른다(새 값 금지). "
        "noticed_first 는 같은 광고라도 사람마다 다르다 — 내 성격·형편·중시 가치에 비추어 "
        "가장 먼저 주의가 가는 요소를 고른다(가격 민감하면 가격, 개방적이면 비주얼 식으로)."
    )


def build_persona_reaction(persona, exposure: str | None, data: dict) -> PersonaReaction:
    """LLM JSON(data)을 §3.5 PersonaReaction으로 파싱(프로바이더 무관) — Gemini·OpenAI 공유."""
    return PersonaReaction(
        persona_id=persona.persona_id,
        exposure_context=exposure,
        aisas=Aisas(**data.get("aisas", {})),
        drop_stage=data.get("drop_stage"),
        drop_reason_tag=data.get("drop_reason_tag"),
        purchase_intent=int(data["purchase_intent"]),
        trust=int(data["trust"]),
        rejected=bool(data.get("rejected", False)),
        rejection_reason_tag=data.get("rejection_reason_tag"),
        emotion_tag=data.get("emotion_tag", EmotionTag.INDIFFERENCE),
        perceived_message=data.get("perceived_message"),
        perceived_target=data.get("perceived_target"),
        brand_recognized=bool(data.get("brand_recognized", False)),
        perceived_brand=data.get("perceived_brand"),
        noticed_first=data.get("noticed_first"),
        utterance=data.get("utterance"),
        qa_passed=True,  # QA 게이트가 별도 판정
    )


async def generate_reaction(json_call, persona, ad: AdInterpretation) -> PersonaReaction:
    """반응 생성 오케스트레이션(프로바이더 무관) — 노출맥락 선택→프롬프트→json_call→파싱.

    json_call: async (prompt:str)->dict. 이 함수만 갈아끼우면 프로바이더(Gemini/OpenAI)가 바뀐다.
    """
    rng = random.Random(persona.persona_id)
    exposure = _pick_exposure(persona, rng)
    data = await json_call(build_reaction_prompt(persona, ad, exposure))
    return build_persona_reaction(persona, exposure, data)


class GeminiReactionEngine:
    """4-b 반응 — §3.5 구조화 JSON 강제(비동기). temperature↑로 페르소나 간 응답 다양성 보존."""

    def __init__(
        self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL, temperature: float = 1.0
    ) -> None:
        self._client = _new_client(api_key)
        self._model = model
        self.version = model
        self._temperature = temperature

    async def react(self, persona, ad: AdInterpretation) -> PersonaReaction:
        async def _json(prompt: str) -> dict:
            return await _agen_json(
                self._client, self._model, prompt, temperature=self._temperature
            )

        return await generate_reaction(_json, persona, ad)
