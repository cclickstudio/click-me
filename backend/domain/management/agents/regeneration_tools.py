"""🅱 재생성 agent 구체 tool — 생성(LLM)·시뮬 점수(SSR)·미리보기(Writer) + 결정론 폴백.

agent(regeneration.py)는 Protocol만 안다 — 구현체는 여기서 만들고 조립 지점에서 주입한다.
타 팀 의존(SSRScorer)은 다시 Protocol(``SsrLike``)로 감싸 인터페이스 변동 리스크를
격리한다 (B-3 단점 대응). API 키 없는 환경(CI·데모 리허설)을 위해 결정론 폴백
(Template 생성·Heuristic 채점)을 함께 제공한다 — 게이트 #9·#10의 B쪽 절반.

불변 규칙 유지: 어떤 tool도 플랫폼 쓰기 API를 호출하지 않는다 — 미리보기는
Writer의 읽기성 메서드(preview)만 사용한다 (§4-1, LLM 출력 → Writer 직접 경로 없음).
단서: 시뮬 점수 ↔ 실제 성과 상관 미검증 — 발표에서 정직하게 공개 (§7).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, Final, Protocol
from uuid import uuid4

from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.agents.regeneration import (
    BANNED_EXPRESSIONS,
    MAX_CANDIDATES,
    CreativeCandidate,
    RegenerationAgent,
)
from domain.management.contracts.enums import AnomalyType

if TYPE_CHECKING:
    from domain.management.contracts.schemas import DiagnosisResult


# ── 생성 tool ① — LLM 기반 (gpt-4o-mini) ────────────────────────────


class ChatModelLike(Protocol):
    """LangChain BaseChatModel 호환 최소 표면 — 테스트는 fake로 대체한다."""

    async def ainvoke(self, input: Any) -> Any: ...  # noqa: A002 — LangChain 시그니처


_GENERATION_SYSTEM_PROMPT = """\
너는 퍼포먼스 광고 카피라이터다. 진단된 게재 이상을 복구하기 위한 새 광고 카피를 만든다.

규칙:
- v1 스코프: 이미지 단일 광고, 캠페인 목표는 트래픽(클릭)만.
- 다음 표현은 절대 사용 금지(심의 가드에서 제거됨): {banned}
- 출력은 JSON 배열 하나만. 코드펜스·설명 금지. 예: ["카피 1", "카피 2"]
- 각 카피는 8~40자의 한국어 한 문장."""

_GENERATION_USER_PROMPT = """\
진단 결과:
- 이상 유형: {anomaly_type}
- 원인 가설: {hypothesis}
- 근거 지표: {evidence}

위 진단을 복구할 광고 카피 {count}개를 JSON 배열로 출력하라."""


def _parse_copies(content: str) -> list[str]:
    """LLM 응답에서 카피 배열을 파싱한다 — 코드펜스 방어 포함, 실패 시 ValueError."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("JSON 배열이 아님")
    copies: list[str] = []
    for item in parsed:
        if isinstance(item, str):
            copies.append(item)
        elif isinstance(item, dict) and isinstance(item.get("ad_copy"), str):
            copies.append(item["ad_copy"])
        else:
            raise ValueError(f"카피 항목 형식 오류: {item!r}")
    if not copies:
        raise ValueError("빈 카피 배열")
    return copies


class LLMCreativeGenerator:
    """CreativeGenerationTool 구현 — LLM이 진단 근거로 새 카피 후보를 만든다.

    파싱 실패는 예외로 올린다 — 재시도/폴백은 agent의 책임이다 (B-3 복구 설계).
    """

    def __init__(
        self,
        llm: ChatModelLike | None = None,
        *,
        model: str = "gpt-4o-mini",
        temperature: float = 0.8,
    ) -> None:
        self._llm = llm
        self._model = model
        self._temperature = temperature

    def _ensure_llm(self) -> ChatModelLike:
        if self._llm is None:
            from langchain_openai import ChatOpenAI  # noqa: PLC0415 — 키 없는 환경 보호

            self._llm = ChatOpenAI(model=self._model, temperature=self._temperature)
        return self._llm

    async def generate(self, diagnosis: DiagnosisResult, count: int) -> list[CreativeCandidate]:
        count = min(count, MAX_CANDIDATES)
        messages = [
            (
                "system",
                _GENERATION_SYSTEM_PROMPT.format(banned=", ".join(BANNED_EXPRESSIONS)),
            ),
            (
                "human",
                _GENERATION_USER_PROMPT.format(
                    anomaly_type=diagnosis.anomaly_type.value,
                    hypothesis=diagnosis.hypothesis or "(없음)",
                    evidence=json.dumps(diagnosis.evidence_metrics, ensure_ascii=False),
                    count=count,
                ),
            ),
        ]
        response = await self._ensure_llm().ainvoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        copies = _parse_copies(content)
        return [
            CreativeCandidate(candidate_id=f"gen_{uuid4().hex[:8]}", ad_copy=copy)
            for copy in copies[:count]
        ]


# ── 생성 tool ② — 결정론 템플릿 폴백 (API 키·비용 없음) ──────────────

_COPY_TEMPLATES: Final[dict[AnomalyType, tuple[str, ...]]] = {
    AnomalyType.BID_LOSS: (
        "지금 가장 주목받는 신제품, 오늘만 특별가",
        "검색 1위 화제의 아이템, 재고 소진 임박",
        "오늘 단 하루, 베스트셀러 한정 혜택",
    ),
    AnomalyType.QUALITY_DEGRADED: (
        "실사용 후기 4.8점, 직접 확인해 보세요",
        "한 달 써본 솔직 리뷰로 증명된 선택",
        "전문가가 추천하는 데일리 필수템",
    ),
    AnomalyType.AUDIENCE_TOO_NARROW: (
        "온 가족이 함께 쓰는 데일리 아이템",
        "처음이라면 더 반가운 입문 구성",
        "누구나 부담 없이 시작하는 베이직 라인",
    ),
}

_DEFAULT_TEMPLATES: Final[tuple[str, ...]] = (
    "지금 확인하면 좋은 오늘의 추천",
    "이번 주 가장 많이 담은 인기 상품",
    "후기로 증명된 베스트 아이템",
)


class TemplateCreativeGenerator:
    """결정론 생성 폴백 — 같은 진단이면 같은 후보 (데모 3회 연속 성공, 게이트 #10)."""

    async def generate(self, diagnosis: DiagnosisResult, count: int) -> list[CreativeCandidate]:
        templates = _COPY_TEMPLATES.get(diagnosis.anomaly_type, _DEFAULT_TEMPLATES)
        return [
            CreativeCandidate(candidate_id=f"tmpl_{index}", ad_copy=copy)
            for index, copy in enumerate(templates[: min(count, MAX_CANDIDATES)])
        ]


# ── 시뮬 점수 tool ① — SSR 어댑터 (타 팀 의존 격리) ──────────────────


class SsrLike(Protocol):
    """tools.simulation.ssr_scorer.SSRScorer 호환 표면 — 변동 리스크 격리용 Port."""

    async def score(self, exposure_text: str) -> dict[str, Any]: ...


class SsrSimulationScorer:
    """SimulationScoreTool 구현 — SSR 분포의 구매의향 평균을 0~1로 정규화한다."""

    def __init__(
        self,
        ssr: SsrLike,
        *,
        dimension: str = "purchase_intent",
        scale_min: float = 1.0,
        scale_max: float = 5.0,
    ) -> None:
        if scale_max <= scale_min:
            raise ValueError("scale_max는 scale_min보다 커야 함")
        self._ssr = ssr
        self._dimension = dimension
        self._scale_min = scale_min
        self._scale_max = scale_max

    async def score(self, candidate: CreativeCandidate) -> float:
        distributions = await self._ssr.score(candidate.ad_copy)
        distribution = distributions[self._dimension]
        mean = distribution.mean if hasattr(distribution, "mean") else distribution["mean"]
        normalized = (float(mean) - self._scale_min) / (self._scale_max - self._scale_min)
        return min(1.0, max(0.0, normalized))


# ── 시뮬 점수 tool ② — 결정론 휴리스틱 폴백 ──────────────────────────

_CTA_KEYWORDS: Final[tuple[str, ...]] = (
    "지금",
    "오늘",
    "특가",
    "할인",
    "무료",
    "한정",
    "베스트",
    "신제품",
)


def _stable_jitter(text: str) -> float:
    """같은 카피 → 같은 지터 (0.0~0.1). 내장 hash는 세션 랜덤이라 사용 금지."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % 1000 / 10_000


class HeuristicSimulationScorer:
    """결정론 채점 폴백 — 카피 표면 특징 기반. SSR 확정 전 데모·CI용."""

    def __init__(self, base: float = 0.45) -> None:
        self._base = base

    async def score(self, candidate: CreativeCandidate) -> float:
        text = candidate.ad_copy
        score = self._base
        if any(keyword in text for keyword in _CTA_KEYWORDS):
            score += 0.15
        if any(ch.isdigit() for ch in text):
            score += 0.10
        score += 0.05 if 8 <= len(text) <= 40 else -0.10
        if any(banned in text for banned in BANNED_EXPRESSIONS):
            score -= 0.30  # 가드가 또 거르지만 점수축에서도 일관되게 불리
        return min(1.0, max(0.0, score + _stable_jitter(text)))


# ── 미리보기 tool — Writer의 읽기성 메서드만 사용 ────────────────────


class MetaPreviewTool:
    """PreviewTool 구현 — MetaAdsWriter.preview(읽기성, idem_key 불요)만 호출한다."""

    def __init__(self, writer: MetaAdsWriter | None = None, settings: object = None) -> None:
        self._writer = writer or MetaAdsWriter(settings)

    async def preview(self, candidate: CreativeCandidate) -> str:
        return await self._writer.preview(candidate.image_ref or candidate.candidate_id)


# ── 조립 헬퍼 — 오케스트레이터(별도 담당)가 쓰는 기본 구성 ────────────


def build_regeneration_agent(
    *,
    settings: object = None,
    llm: ChatModelLike | None = None,
    ssr: SsrLike | None = None,
    preview_writer: MetaAdsWriter | None = None,
    **agent_kwargs: Any,
) -> RegenerationAgent:
    """기본 tool 구성으로 RegenerationAgent를 조립한다.

    - 생성: llm 주입 또는 openai 키가 있으면 LLM, 없으면 결정론 템플릿 폴백
    - 채점: ssr 주입 시 SSR 정규화, 없으면 결정론 휴리스틱 폴백
    - 미리보기: MetaAdsWriter.preview (stub은 페이스북 미리보기 URL 형식 반환)
    """
    use_llm = llm is not None or bool(getattr(settings, "openai_api_key", None))
    generator = LLMCreativeGenerator(llm=llm) if use_llm else TemplateCreativeGenerator()
    scorer = SsrSimulationScorer(ssr) if ssr is not None else HeuristicSimulationScorer()
    preview = MetaPreviewTool(writer=preview_writer, settings=settings)
    return RegenerationAgent(generator=generator, scorer=scorer, preview=preview, **agent_kwargs)
