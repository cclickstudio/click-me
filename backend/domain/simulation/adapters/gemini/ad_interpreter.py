# 광고해석 어댑터 — 카피(ad_content) + 크리에이티브 이미지(ad_image_url)를 VLM으로 구조화.
from __future__ import annotations

from typing import Any

from domain.simulation.adapters.gemini._common import (
    _DEFAULT_MODEL,
    _agen_json,
    _load_image,
    _new_client,
)
from domain.simulation.contracts.schemas import AdInterpretation, SimulationRunRequest


class GeminiAdInterpreter:
    """광고해석 — 텍스트·이미지 멀티모달. 업종·타깃·메시지 구조화 추출."""

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
