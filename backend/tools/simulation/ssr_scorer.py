import numpy as np
from openai import AsyncOpenAI

from core.schemas import ScoreDistribution
from tools.simulation.anchors import ANCHOR_STATEMENTS, SCORE_RANGES, EMBEDDING_MODEL


class SSRScorer:
    """
    Semantic Similarity Rating (SSR) scorer.
    Exposure + Deliberation text → embeddings → cosine similarity with anchor statements → score distribution.
    Deterministic: same input → same output. No LLM calls — embedding API only.
    Must call precompute_anchors() once at server startup.
    """

    def __init__(self) -> None:
        self.client = AsyncOpenAI()
        self._anchor_embeddings: dict[str, np.ndarray] = {}

    async def precompute_anchors(self) -> None:
        all_anchors: list[str] = []
        index_map: list[tuple[str, int]] = []
        for dim, anchors in ANCHOR_STATEMENTS.items():
            for i, anchor in enumerate(anchors):
                all_anchors.append(anchor)
                index_map.append((dim, i))

        response = await self.client.embeddings.create(model=EMBEDDING_MODEL, input=all_anchors)

        by_dim: dict[str, list[list[float]]] = {d: [] for d in ANCHOR_STATEMENTS}
        for (dim, _), emb_obj in zip(index_map, response.data):
            by_dim[dim].append(emb_obj.embedding)

        for dim, emb_list in by_dim.items():
            self._anchor_embeddings[dim] = np.array(emb_list, dtype=np.float32)

    async def score(self, exposure_text: str) -> dict[str, ScoreDistribution]:
        resp = await self.client.embeddings.create(model=EMBEDDING_MODEL, input=[exposure_text])
        response_emb = np.array(resp.data[0].embedding, dtype=np.float32)

        scores: dict[str, ScoreDistribution] = {}
        rng = np.random.default_rng(42)

        for dim, anchor_embs in self._anchor_embeddings.items():
            anchor_norms = np.linalg.norm(anchor_embs, axis=1)
            response_norm = float(np.linalg.norm(response_emb))
            cosine_sims = (anchor_embs @ response_emb) / (anchor_norms * response_norm + 1e-9)

            shifted = cosine_sims - cosine_sims.min()
            probs = shifted / (shifted.sum() + 1e-9)

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
