"""🅱 재생성 agent 구체 tool — 4-3 생성 위임(HTTP)·미리보기(Writer) + 데모용 템플릿 mock.

agent(regeneration.py)는 Protocol만 안다 — 구현체는 여기서 만들고 조립 지점에서 주입한다.
B는 시안을 만들지도 채점하지도 않는다 — 생성·순위는 4-3 도메인의 공개 HTTP API(IMPROVE)로
위임하고, copy 객체·idx는 합성 없이 그대로 통과시킨다. TemplateCreativeGenerator는 키·서버
없는 데모/테스트에서 4-3을 대신하는 결정론 mock일 뿐 — 실패 폴백이 아니다(스펙 §5e).

불변 규칙 유지: 어떤 tool도 플랫폼 쓰기 API를 호출하지 않는다 — 미리보기는
Writer의 읽기성 메서드(preview)만 사용한다 (§4-1, LLM 출력 → Writer 직접 경로 없음).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, Final, Protocol

from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.agents.regeneration import (
    MAX_CANDIDATES,
    CreativeCandidate,
    RemediationAgent,
)
from domain.management.contracts.enums import AnomalyType

if TYPE_CHECKING:
    from domain.management.agents.selection import SelectionRoundRepository
    from domain.management.contracts.schemas import DiagnosisResult


# ── 생성 mock — 결정론 템플릿 (데모/테스트에서 4-3 대역) ──────────────

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
    """결정론 생성 mock — 같은 진단이면 같은 후보 (데모 3회 연속 성공, 게이트 #10).

    4-3 실연동 전·키 없는 환경에서 4-3을 대신하는 mock(primary로 주입). 실패 폴백이 아니다.
    """

    async def generate(self, diagnosis: DiagnosisResult, count: int) -> list[CreativeCandidate]:
        templates = _COPY_TEMPLATES.get(diagnosis.anomaly_type, _DEFAULT_TEMPLATES)
        # mock은 새 시안을 만든다(GENERATED_NEW) — guard asset 규칙을 위해 s3_key를 채운다.
        return [
            CreativeCandidate(
                candidate_id=f"tmpl_{index}",
                copy=copy,
                idx=index,
                image_ref=f"s3/mock/tmpl_{index}.png",
            )
            for index, copy in enumerate(templates[: min(count, MAX_CANDIDATES)])
        ]


# ── 미리보기 tool — Writer의 읽기성 메서드만 사용 ────────────────────


class MetaPreviewTool:
    """PreviewTool 구현 — MetaAdsWriter.preview(읽기성, idem_key 불요)만 호출한다."""

    def __init__(self, writer: MetaAdsWriter | None = None, settings: object = None) -> None:
        self._writer = writer or MetaAdsWriter(settings)

    async def preview(self, candidate: CreativeCandidate) -> str:
        return await self._writer.preview(candidate.image_ref or candidate.candidate_id)


# ── 생성 tool — generator 도메인 HTTP 어댑터 (IMPROVE) ───────────────


class GeneratorInputError(ValueError):
    """IMPROVE 호출에 필요한 입력(기존 크리에이티브 s3_key)이 진단에 없음 → 폴백 신호."""


class AsyncHttpClient(Protocol):
    """generator HTTP API 호출에 쓰는 최소 표면 — 테스트는 fake로 대체한다."""

    async def post(self, url: str, json: dict[str, Any]) -> Any: ...  # noqa: A002

    async def get(self, url: str) -> Any: ...


def _summarize_diagnosis(diagnosis: DiagnosisResult) -> str:
    """진단을 generator IMPROVE의 simulation_summary 문자열로 합성 (s3_key는 제외)."""
    parts = [f"이상 유형: {diagnosis.anomaly_type.value}"]
    if diagnosis.hypothesis:
        parts.append(f"가설: {diagnosis.hypothesis}")
    evidence = {k: v for k, v in diagnosis.evidence_metrics.items() if k != "existing_ad_s3_key"}
    if evidence:
        parts.append(f"근거: {json.dumps(evidence, ensure_ascii=False)}")
    return " / ".join(parts)


class GeneratorHttpTool:
    """CreativeGenerationTool 구현 — generator 도메인의 공개 HTTP API(IMPROVE)를 호출한다.

    도메인 경계 준수: generator 내부를 import하지 않고 HTTP 표면에만 의존한다
    (의존 계약 = POST /generations(IMPROVE) 요청 + GET /generations/{id} 응답 모양).
    생성은 백그라운드 작업이라 GET으로 완료까지 폴링하고, 초과 시 TimeoutError(→폴백).
    필수 입력 existing_ad_s3_key는 진단 evidence에서 읽는다 — 없으면 GeneratorInputError.
    copy 객체·idx·explanation은 합성 없이 그대로 통과시킨다 (B는 채점·합성 안 함).
    """

    def __init__(
        self,
        client: AsyncHttpClient,
        *,
        base_url: str = "/api/generator",
        poll_interval: float = 0.5,
        timeout_s: float = 30.0,
        clock: Any = None,
        sleep: Any = None,
    ) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._poll_interval = poll_interval
        self._timeout_s = timeout_s
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep

    async def generate(self, diagnosis: DiagnosisResult, count: int) -> list[CreativeCandidate]:
        s3_key = diagnosis.evidence_metrics.get("existing_ad_s3_key")
        if not s3_key:
            raise GeneratorInputError("진단에 existing_ad_s3_key가 없어 IMPROVE 호출 불가")
        body = {
            "mode": "improve",
            "existing_ad_s3_key": s3_key,
            "simulation_summary": _summarize_diagnosis(diagnosis),
            "fix_requests": diagnosis.hypothesis or None,
        }
        post = await self._client.post(f"{self._base}/generations", json=body)
        generation_id = post.json()["generation_id"]
        detail = await self._poll(generation_id)
        candidates = detail.get("candidates", [])[:count]
        return [
            CreativeCandidate(
                candidate_id=c["candidate_id"],
                copy=c["copy"],
                idx=c.get("idx"),
                image_ref=c.get("s3_key"),
                explanation=c.get("explanation"),
            )
            for c in candidates
        ]

    async def _poll(self, generation_id: str) -> dict[str, Any]:
        start = self._clock()
        url = f"{self._base}/generations/{generation_id}"
        while True:
            detail = (await self._client.get(url)).json()
            status = detail.get("status")
            if status == "completed":
                return detail
            if status == "failed":
                raise RuntimeError(f"generator 생성 실패: {generation_id}")
            if self._clock() - start >= self._timeout_s:
                raise TimeoutError(f"generator 생성 타임아웃: {generation_id}")
            await self._sleep(self._poll_interval)


# ── 조립 헬퍼 — 오케스트레이터(별도 담당)가 쓰는 기본 구성 ────────────


def build_regeneration_agent(
    *,
    settings: object = None,
    preview_writer: MetaAdsWriter | None = None,
    generator_client: AsyncHttpClient | None = None,
    selection_store: SelectionRoundRepository | None = None,
    **agent_kwargs: Any,
) -> RemediationAgent:
    """기본 tool 구성으로 RemediationAgent를 조립한다.

    - 생성: generator_client 주입 시 generator HTTP(IMPROVE) 단독 — 폴백 없음
            (4-3 실패=빈손 → candidate_count 분기에서 CREATIVE_UNAVAILABLE).
            아니면 TemplateCreativeGenerator(데모/테스트 mock 4-3).
    - 미리보기: MetaAdsWriter.preview (stub은 페이스북 미리보기 URL 형식 반환)
    - 선택 라운드: 주입 없으면 InMemorySelectionRoundStore (v1 단일 프로세스).
    """
    from domain.management.agents.selection import InMemorySelectionRoundStore

    if generator_client is not None:
        generator: Any = GeneratorHttpTool(generator_client)  # 운영 — 생성 폴백 없음
    else:
        generator = TemplateCreativeGenerator()  # 데모/테스트 mock 4-3
    preview = MetaPreviewTool(writer=preview_writer, settings=settings)
    return RemediationAgent(
        generator=generator,
        preview=preview,
        selection_store=selection_store or InMemorySelectionRoundStore(),
        **agent_kwargs,
    )
