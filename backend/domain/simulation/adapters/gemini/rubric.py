# 루브릭 평가 어댑터 — 광고(해석)를 차원별 0~100 점수화. 광고에만 의존(반응과 병렬).
from __future__ import annotations

from domain.simulation.adapters.gemini._common import _DEFAULT_MODEL, _agen_json, _new_client
from domain.simulation.contracts.schemas import AdInterpretation, RubricScore

_RUBRIC_DIMENSIONS = ("clarity", "relevance", "trust", "creativity", "cta_strength")


class GeminiRubricEvaluator:
    """루브릭 평가 — 차원별 0~100 점수 + 근거(JSON)."""

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
