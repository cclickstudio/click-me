# 광고해석 어댑터 — 카피(ad_content) + 크리에이티브 이미지(ad_image_url)를 VLM으로 구조화.
from __future__ import annotations

from typing import Any

from domain.simulation.adapters.gemini._common import (
    _DEFAULT_MODEL,
    _agen_json,
    _load_image,
    _new_client,
)
from domain.simulation.contracts.schemas import (
    AdFeatures,
    AdInterpretation,
    SimulationRunRequest,
)

# AdFeatures 로 추려 담을 키 — LLM JSON 중 광고 특성 필드만 통과(나머지는 무시).
_FEATURE_KEYS = (
    "ad_credibility",
    "ad_quality",
    "price_mentioned",
    "original_price",
    "discounted_price",
    "brand_mentioned",
    "social_proof_strength",
)


class GeminiAdInterpreter:
    """광고해석 — 텍스트·이미지 멀티모달. 업종·타깃·메시지 구조화 추출."""

    def __init__(self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._client = _new_client(api_key)
        self._model = model
        self.version = model

    async def interpret(self, request: SimulationRunRequest) -> AdInterpretation:
        if not request.ad_content and not request.ad_image_url:
            return AdInterpretation(ad_id=request.ad_id, model_version=f"{self.version}-empty")
        # 앵커링 방지(§3.5-3) — 선언 의도(product_category·ad_objective·ad_title)는 주입하지 않는다.
        prompt = (
            "다음 광고(카피/이미지)를 분석해 아래 JSON만 출력하라(코드펜스 없이).\n"
            '{"detected_industry": "업종/제품 카테고리", "detected_objective": "광고 목적'
            '(인지/구매전환/브랜딩 등)", "detected_target": "핵심 타깃", '
            '"detected_message": "핵심 메시지 한 문장", '
            '"ad_credibility": 0~100 정수(증거·현실성·정직성), '
            '"ad_quality": 0~100 정수(명확성·매력·구조·CTA), '
            '"price_mentioned": bool, "original_price": 정가 숫자 또는 null, '
            '"discounted_price": 할인가 숫자 또는 null, "brand_mentioned": bool, '
            '"social_proof_strength": "high"|"medium"|"low"|"none", '
            # 시각 요소 인벤토리(§4-a) — structured_analysis(JSONB)에 담겨 반응 프롬프트로 흐른다.
            '"visual_elements": {"primary_subject": "가장 부각되는 피사체(인물/제품/텍스트 등)", '
            '"elements": ["눈에 띄는 시각 요소 나열(모델 얼굴·제품샷·로고·CTA버튼·배경 등)"], '
            '"first_impression": "첫눈에 가장 먼저 들어오는 요소 한 가지", '
            '"color_tone": "전반 색감·톤 한 구절"}, '
            # 브랜드 시대성(Tier 2) — 유명 브랜드 특정 시에만.
            # structured_analysis(JSONB)에 1회 추출해 전 페르소나 공유.
            '"brand_era": {"identified": bool(특정 유명 브랜드/제품으로 식별했는가), '
            '"era": "그 브랜드가 가장 친숙·전성기였던 시기 한 구절'
            '(예: 1990년대/2010년대/전세대 꾸준), 모르면 null", '
            '"generational_skew": "all"|"older"|"younger"|"unknown", '
            '"note": "세대 관련성 한 구절(예: 90년대 국민 음료·중장년 향수), 모르면 null"}}\n'
            "유명 브랜드를 특정 못 하면 brand_era.identified=false 로 두고 "
            "시대를 지어내지 마라.\n\n"
            f"[광고 카피]\n{request.ad_content or '(텍스트 없음 — 이미지 참고)'}"
        )
        contents: Any = prompt
        used_vision = False
        if request.ad_image_url:
            from google.genai import types

            data, mime = await _load_image(request.ad_image_url)
            contents = [prompt, types.Part.from_bytes(data=data, mime_type=mime)]
            used_vision = True
        result = await _agen_json(
            self._client, self._model, contents, langsmith_extra={"name": "simulation.ad_interpret"}
        )
        # 광고 특성은 result(structured_analysis)에 그대로 영속되고, 타입 객체로도 추려 흐른다.
        features = AdFeatures(**{k: result[k] for k in _FEATURE_KEYS if k in result})
        return AdInterpretation(
            ad_id=request.ad_id,
            structured_analysis=result,
            detected_industry=result.get("detected_industry"),
            detected_objective=result.get("detected_objective"),
            detected_target=result.get("detected_target"),
            detected_message=result.get("detected_message"),
            ad_features=features,
            model_version=f"{self.version}-vision" if used_vision else self.version,
        )
