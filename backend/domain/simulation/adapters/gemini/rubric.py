# 의도 정합 채점 어댑터 — 선언 의도 ↔ VLM 감지 의도를 차원별 0~100으로 비교(§3.5-3).
#
# 앵커링 방지: 감지(ad_interpreter)와 분리된 별도 콜에서 비교만 수행. 광고에만 의존.
from __future__ import annotations

from domain.simulation.adapters.gemini._common import _DEFAULT_MODEL, _agen_json, _new_client
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    RubricScore,
    SimulationRunRequest,
)

# (정합 차원, 선언 필드 라벨, 감지값 접근자) — 선언 입력이 있는 차원만 채점.
_ALIGN_DIMS = (
    ("category_alignment", "제품 카테고리", "detected_industry"),
    ("objective_alignment", "캠페인 목표", "detected_objective"),
    ("message_alignment", "광고 제목/핵심 메시지", "detected_message"),
)


class GeminiRubricEvaluator:
    """의도 정합 채점 — 차원별 0~100 정합 점수 + 근거(declared/detected/note)."""

    def __init__(self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._client = _new_client(api_key)
        self._model = model
        self.version = model

    async def evaluate(
        self, ad: AdInterpretation, request: SimulationRunRequest
    ) -> list[RubricScore]:
        # 선언값(시뮬레이터 탭 입력) — 차원별 (선언, 감지) 쌍을 만든다. 선언 미입력 차원은 스킵.
        declared = {
            "category_alignment": request.product_category,
            "objective_alignment": request.ad_objective,
            "message_alignment": request.ad_title,
        }
        pairs = [
            (dim, declared[dim], getattr(ad, attr))
            for dim, _label, attr in _ALIGN_DIMS
            if declared[dim]
        ]
        if not pairs:  # 선언 입력이 하나도 없으면 교차검증 스킵
            return []

        lines = "\n".join(f"- {dim}: 선언='{dec}' / 감지='{det or ''}'" for dim, dec, det in pairs)
        prompt = (
            "광고주가 **선언한 의도**와 VLM이 **감지한 의도**가 얼마나 일치하는지 차원별로 "
            "0~100 정합 점수와 한 줄 근거를 매겨 JSON만 출력하라"
            "(라벨이 달라도 핵심 의미가 같으면 高).\n"
            f"차원·값:\n{lines}\n\n"
            '형식: {"category_alignment": {"score": int, "note": "근거"}, ...} '
            "(주어진 차원만 출력)"
        )
        data = await _agen_json(self._client, self._model, prompt)
        scores: list[RubricScore] = []
        for dim, dec, det in pairs:
            item = data.get(dim) or {}
            raw = item.get("score", 0) if isinstance(item, dict) else item
            score = max(0, min(100, int(raw)))
            note = item.get("note", "") if isinstance(item, dict) else ""
            scores.append(
                RubricScore(
                    dimension=dim,
                    score=score,
                    evidence={"declared": dec, "detected": det, "note": note},
                )
            )
        return scores
