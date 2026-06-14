# 실 LLM 어댑터(P4) — google-genai(async)로 광고해석(VLM 포함)·반응(§3.5)·루브릭·QA.
#
# 원칙: 숫자(집계)는 코드, "문장·반응"만 LLM. 반응은 §3.5 구조화 JSON 강제(자유텍스트 금지).
# 다양성 보존 위해 반응 temperature 높게. core.config 미의존(키 주입), 모델 핀.
# 전 호출 비동기(client.aio) → fan-out N개가 직렬화 없이 동시 진행. QA는 규칙 선검사 후 LLM(opt-in).
from __future__ import annotations

import json
import mimetypes
import os
import random
from pathlib import Path
from typing import Any

import httpx

from domain.simulation.contracts.enums import (
    AisasStage,
    DropReasonTag,
    EmotionTag,
    RejectionReasonTag,
)
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    PersonaReaction,
    RubricScore,
    SimulationRunRequest,
)

_DEFAULT_MODEL = "gemini-2.5-flash"  # 재현성 위해 버전 핀
_RUBRIC_DIMENSIONS = ("clarity", "relevance", "trust", "creativity", "cta_strength")


def _enum_values(enum_cls) -> str:
    return ", ".join(e.value for e in enum_cls)


def _new_client(api_key: str | None) -> Any:
    from google import genai

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 미설정 — 실 LLM 어댑터 불가")
    return genai.Client(api_key=key)


async def _agen_json(
    client: Any, model: str, contents: Any, *, temperature: float | None = None
) -> dict:
    """google-genai 비동기 호출 + JSON 파싱. contents는 str 또는 [str, 이미지 Part] 리스트."""
    config: dict[str, Any] = {"response_mime_type": "application/json"}
    if temperature is not None:
        config["temperature"] = temperature
    resp = await client.aio.models.generate_content(model=model, contents=contents, config=config)
    return _parse_json(getattr(resp, "text", "") or "")


async def _load_image(url: str) -> tuple[bytes, str]:
    """광고 이미지 로드 → (bytes, mime). http(s)는 httpx, 그 외는 로컬 경로."""
    if url.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(url)
            r.raise_for_status()
            mime = (r.headers.get("content-type") or "image/jpeg").split(";")[0]
            return r.content, mime
    data = Path(url).read_bytes()
    return data, (mimetypes.guess_type(url)[0] or "image/jpeg")


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출 — 코드펜스 제거 후 파싱."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        t = t[4:].strip() if t.lower().startswith("json") else t.strip()
    return json.loads(t)


def _pick_exposure(persona, rng: random.Random) -> str | None:
    cands = persona.media_behavior.get("exposure_candidates") or []
    if not cands:
        return None
    e = rng.choice(cands)
    return f"{e['timeband']}·{e['place']}·{e['medium']}·{e['activity']}"


def _rule_check(reaction: PersonaReaction) -> tuple[bool, str | None]:
    """규칙 기반 일관성 검사(무콜) — AISAS 깔때기·필수 필드. LLM QA의 선검사로도 사용."""
    a = reaction.aisas
    if a.action and not (a.attention and a.interest):
        return False, "aisas_funnel_inconsistent"  # action엔 attention·interest 선행 필요
    if a.interest and not a.attention:
        return False, "aisas_funnel_inconsistent"
    if not (reaction.utterance or "").strip():
        return False, "empty_utterance"
    return True, None


class GeminiReactionEngine:
    """4-b 반응 — 페르소나가 광고에 '한 사람처럼' 반응. §3.5 구조화 JSON 강제(비동기)."""

    def __init__(
        self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL, temperature: float = 1.0
    ) -> None:
        self._client = _new_client(api_key)
        self._model = model
        self.version = model
        self._temperature = temperature  # 높게 → 페르소나 간 응답 다양성 보존(동질화 방지)

    def _prompt(self, persona, ad: AdInterpretation, exposure: str | None) -> str:
        income = persona.socioeconomic.get("income_bracket", "?")
        edu = persona.socioeconomic.get("education", "?")
        values = [k for k, v in persona.consumption_values.items() if v]
        return (
            "당신은 아래 한국 소비자 '본인'입니다. 이 사람의 성격·형편·미디어 습관에 충실하게, "
            "주어진 광고에 솔직하게 반응하세요. 교과서적 정답이 아니라 이 사람의 실제 반응을.\n\n"
            f"[나]\n- {persona.age}세 {persona.gender}, {persona.region}\n"
            f"- 학력 {edu}, 월소득 {income}\n"
            f"- OCEAN(표준화, 양수=평균이상): {persona.ocean}\n"
            f"- 주 이용 미디어: {persona.media_behavior.get('primary_medium', '?')}\n"
            f"- 중시 소비가치: {values}\n"
            f"- 서사: {persona.profile_narrative or '(없음)'}\n"
            f"- 지금 노출 맥락: {exposure or '일반'}\n\n"
            f"[광고]\n- 업종: {ad.detected_industry}\n- 메시지: {ad.detected_message}\n"
            f"- 추정 타깃: {ad.detected_target}\n\n"
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
            '  "utterance": "한 문장 솔직한 반응"\n'
            "}\n"
            "주의: AISAS는 깔때기 — action=true면 attention·interest도 true여야 한다. "
            "태그는 반드시 제시된 값에서만 고른다(새 값 금지)."
        )

    async def react(self, persona, ad: AdInterpretation) -> PersonaReaction:
        rng = random.Random(persona.persona_id)
        exposure = _pick_exposure(persona, rng)
        data = await _agen_json(
            self._client,
            self._model,
            self._prompt(persona, ad, exposure),
            temperature=self._temperature,
        )
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
            utterance=data.get("utterance"),
            qa_passed=True,  # QA 게이트가 별도 판정
        )


class GeminiAdInterpreter:
    """광고해석 — 카피(ad_content) + 크리에이티브 이미지(ad_image_url)를 VLM으로 구조화."""

    def __init__(self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._client = _new_client(api_key)
        self._model = model
        self.version = model

    async def interpret(self, request: SimulationRunRequest) -> AdInterpretation:
        if not request.ad_content and not request.ad_image_url:
            return AdInterpretation(ad_id=request.ad_id, model_version=f"{self.version}-empty")
        prompt = (
            "다음 광고(카피/이미지)를 분석해 아래 JSON만 출력하라(코드펜스 없이).\n"
            '{"detected_industry": "업종", "detected_target": "핵심 타깃", '
            '"detected_message": "핵심 메시지 한 문장"}\n\n'
            f"[광고 카피]\n{request.ad_content or '(텍스트 없음 — 이미지 참고)'}"
        )
        contents: Any = prompt
        used_vision = False
        if request.ad_image_url:
            from google.genai import types

            data, mime = await _load_image(request.ad_image_url)
            contents = [prompt, types.Part.from_bytes(data=data, mime_type=mime)]
            used_vision = True
        result = await _agen_json(self._client, self._model, contents)
        return AdInterpretation(
            ad_id=request.ad_id,
            structured_analysis=result,
            detected_industry=result.get("detected_industry"),
            detected_target=result.get("detected_target"),
            detected_message=result.get("detected_message"),
            model_version=f"{self.version}-vision" if used_vision else self.version,
        )


class GeminiRubricEvaluator:
    """루브릭 평가 — 광고(해석)를 차원별 0~100 점수화. 광고에만 의존(반응과 병렬)."""

    def __init__(self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._client = _new_client(api_key)
        self._model = model
        self.version = model

    async def evaluate(self, ad: AdInterpretation) -> list[RubricScore]:
        dims = ", ".join(_RUBRIC_DIMENSIONS)
        prompt = (
            "다음 광고를 아래 차원별로 0~100 점수와 한 줄 근거를 매겨 JSON만 출력하라.\n"
            f"차원: {dims}\n"
            '형식: {"clarity": {"score": int, "evidence": "근거"}, ...}\n\n'
            f"[광고]\n업종 {ad.detected_industry} / 타깃 {ad.detected_target} / "
            f"메시지 {ad.detected_message}\n구조화: {ad.structured_analysis}"
        )
        data = await _agen_json(self._client, self._model, prompt)
        scores: list[RubricScore] = []
        for dim in _RUBRIC_DIMENSIONS:
            item = data.get(dim) or {}
            score = int(item.get("score", 0)) if isinstance(item, dict) else int(item)
            scores.append(
                RubricScore(
                    dimension=dim,
                    score=max(0, min(100, score)),
                    evidence={"note": (item.get("evidence", "") if isinstance(item, dict) else "")},
                )
            )
        return scores


class RuleQaGate:
    """QA 검문소 — 규칙 기반(무콜). AISAS 깔때기·필수 필드 일관성. 인터페이스 통일로 async."""

    async def check(
        self, reaction: PersonaReaction, attempt: int, *, persona=None, ad=None
    ) -> tuple[bool, str | None]:
        return _rule_check(reaction)


class GeminiQaGate:
    """QA 검문소 — 규칙 선검사(무콜) 후 통과분만 LLM 일관성 검증(비동기, opt-in).

    콜 2배 방지: 규칙에서 떨어지면 LLM 호출 없이 즉시 탈락. 비동기라 fan-out에서 직렬화 없음.
    """

    def __init__(self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._client = _new_client(api_key)
        self._model = model

    async def check(
        self, reaction: PersonaReaction, attempt: int, *, persona=None, ad=None
    ) -> tuple[bool, str | None]:
        ok, reason = _rule_check(reaction)
        if not ok:
            return ok, reason  # 규칙 탈락 → LLM 콜 생략
        income = getattr(persona, "socioeconomic", {}).get("income_bracket", "?")
        prompt = (
            "아래는 한 소비자가 광고에 보인 반응이다. 이 반응이 (a) 광고와 무관하지 않고 "
            "(b) 소비자 설정과 모순되지 않으며 (c) 앞뒤(구조화 값↔발화)가 일치하는지 판정하라.\n"
            'JSON만 출력: {"pass": true/false, "reason": "탈락 시 짧은 사유"}\n\n'
            f"[소비자] {getattr(persona, 'age', '?')}세 {getattr(persona, 'gender', '?')}, "
            f"소득 {income}\n"
            f"[광고] {getattr(ad, 'detected_message', '?')} "
            f"(타깃 {getattr(ad, 'detected_target', '?')})\n"
            f"[반응] 구매의도 {reaction.purchase_intent}/5, 신뢰 {reaction.trust}/5, "
            f"거부 {reaction.rejected}, 감정 {reaction.emotion_tag}, "
            f"인식메시지 '{reaction.perceived_message}', 발화 '{reaction.utterance}'"
        )
        try:
            data = await _agen_json(self._client, self._model, prompt)
        except Exception:
            return True, None  # LLM QA 실패 시 보수적 통과(런 유지) — 규칙은 이미 통과
        if data.get("pass", True):
            return True, None
        return False, f"llm_qa: {data.get('reason', 'inconsistent')}"
