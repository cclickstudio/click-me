import hashlib
import os

import numpy as np
from openai import AsyncOpenAI

from core.schemas import ScoreDistribution
from tools.simulation.anchors import ANCHOR_STATEMENTS, EMBEDDING_MODEL, SCORE_RANGES, SOFTMAX_TAU


class SSRScorer:
    """
    Semantic Similarity Rating (SSR) scorer.
    반응 서술 텍스트 → 임베딩 → 앵커(레벨당 복수 문장 평균)와 코사인 유사도 → softmax 분포.
    Deterministic: same input → same output. No LLM calls — embedding API only.
    Must call precompute_anchors() once at server startup.
    """

    def __init__(self) -> None:
        self.use_mock = os.getenv("USE_MOCK", "").lower() in {"1", "true", "yes", "on"}
        self.client = None if self.use_mock else AsyncOpenAI()
        self._anchor_embeddings: dict[str, np.ndarray] = {}

    async def precompute_anchors(self) -> None:
        # 레벨당 복수 문장(v2.0) — 문장 전부를 한 번에 임베딩한 뒤 레벨별 평균을 앵커로 쓴다.
        all_anchors: list[str] = []
        index_map: list[tuple[str, int]] = []
        for dim, levels in ANCHOR_STATEMENTS.items():
            for i, level in enumerate(levels):
                for anchor in level:
                    all_anchors.append(anchor)
                    index_map.append((dim, i))

        by_level: dict[tuple[str, int], list[list[float]]] = {}
        if self.use_mock:
            embeddings = self._mock_embeddings(all_anchors)
            for key, embedding in zip(index_map, embeddings, strict=False):
                by_level.setdefault(key, []).append(embedding)
        else:
            if self.client is None:
                raise RuntimeError("SSR scorer OpenAI client is not initialized.")
            response = await self.client.embeddings.create(model=EMBEDDING_MODEL, input=all_anchors)
            for key, emb_obj in zip(index_map, response.data, strict=False):
                by_level.setdefault(key, []).append(emb_obj.embedding)

        for dim, levels in ANCHOR_STATEMENTS.items():
            level_means = [
                np.array(by_level[(dim, i)], dtype=np.float32).mean(axis=0)
                for i in range(len(levels))
            ]
            self._anchor_embeddings[dim] = np.array(level_means, dtype=np.float32)

    async def score(self, exposure_text: str) -> dict[str, ScoreDistribution]:
        if not self._anchor_embeddings:
            raise RuntimeError(
                "SSR scorer is not initialized. "
                "Anchor precomputation failed at startup — check OpenAI API quota."
            )
        if self.use_mock:
            response_emb = np.array(self._mock_embeddings([exposure_text])[0], dtype=np.float32)
        else:
            if self.client is None:
                raise RuntimeError("SSR scorer OpenAI client is not initialized.")
            resp = await self.client.embeddings.create(model=EMBEDDING_MODEL, input=[exposure_text])
            response_emb = np.array(resp.data[0].embedding, dtype=np.float32)

        scores: dict[str, ScoreDistribution] = {}
        rng = np.random.default_rng(42)

        for dim, anchor_embs in self._anchor_embeddings.items():
            anchor_norms = np.linalg.norm(anchor_embs, axis=1)
            response_norm = float(np.linalg.norm(response_emb))
            cosine_sims = (anchor_embs @ response_emb) / (anchor_norms * response_norm + 1e-9)

            # softmax 온도 정규화(v2.0) — 구 min-shift는 유사도 미세 차이를 뭉개
            # 분산 뭉개짐·극성 역전을 일으켰다(P08). τ는 anchors.SOFTMAX_TAU.
            exp = np.exp((cosine_sims - cosine_sims.max()) / SOFTMAX_TAU)
            probs = exp / (exp.sum() + 1e-9)

            lo, hi = SCORE_RANGES[dim]
            levels = np.linspace(lo, hi, len(probs))
            expected = float(np.dot(probs, levels))
            std = float(np.sqrt(np.dot(probs, (levels - expected) ** 2)))
            sampled = rng.choice(levels, size=2000, p=probs)

            scores[dim] = ScoreDistribution(
                mean=expected,
                std=std,
                p10=float(np.percentile(sampled, 10)),
                p90=float(np.percentile(sampled, 90)),
                raw_probs=probs.tolist(),
            )

        return scores

    @staticmethod
    def _mock_embeddings(texts: list[str], dim: int = 64) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            seed = int.from_bytes(digest[:8], "big", signed=False)
            rng = np.random.default_rng(seed)
            vec = rng.normal(size=dim).astype(np.float32)
            vec /= np.linalg.norm(vec) + 1e-9
            embeddings.append(vec.tolist())
        return embeddings

    @staticmethod
    def build_input_text(exposure: dict, deliberation: dict) -> str:
        return (
            f"시선집중: {exposure.get('attention_capture', '')}\n"
            f"첫감정: {exposure.get('first_emotion', '')}\n"
            f"본능반응: {exposure.get('gut_reaction', '')}\n"
            f"스크롤결정: {exposure.get('scroll_decision', '')}\n"
            f"지지생각: {'; '.join(deliberation.get('supporting_thoughts', []))}\n"
            f"반대생각: {'; '.join(deliberation.get('opposing_thoughts', []))}\n"
            f"가치일치: {deliberation.get('value_alignment', '')}\n"
            f"최종태도: {deliberation.get('final_attitude', '')}"
        )
