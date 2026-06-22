# generator D1 계약(GET /generations/{id})을 HTTP로 읽어 핸드오프 후보를 해소하는 어댑터

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_EXPECTED_SCHEMA = "1"
_TIMEOUT = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=5.0)
_RETRIES = 1


class InvalidGenerationError(Exception):
    """generation/candidate가 핸드오프에 부적합 — http_status로 라우터가 응답 코드 결정."""

    def __init__(self, http_status: int, detail: str) -> None:
        super().__init__(detail)
        self.http_status = http_status
        self.detail = detail


class GeneratorUnavailableError(Exception):
    """generator 서버 불통/5xx — 라우터가 502로 변환."""


class HandoffCopy(BaseModel):
    headline: str
    body: str
    cta: str = ""


class HandoffCandidate(BaseModel):
    candidate_id: str
    idx: int
    strategy: str = ""
    template_id: str = ""
    copy: HandoffCopy
    s3_key: str


class GeneratorReadClient:
    """generator 응답을 검증·파싱해 HandoffCandidate를 돌려준다. generator 내부 타입 import 금지."""

    def __init__(self, *, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def get_candidate(self, generation_id: str, candidate_id: str) -> HandoffCandidate:
        data = await self._fetch(generation_id)
        if data.get("schema_version") != _EXPECTED_SCHEMA:
            # 스펙 D1 — 계약 버전 불일치는 generator 팀 알림 대상. 감사/모니터링용 로그.
            logger.error(
                "generator D1 schema_version 불일치 generation=%s got=%s expected=%s",
                generation_id,
                data.get("schema_version"),
                _EXPECTED_SCHEMA,
            )
            raise InvalidGenerationError(
                409, f"지원하지 않는 schema_version: {data.get('schema_version')}"
            )
        if data.get("status") != "completed":
            raise InvalidGenerationError(409, f"생성 미완료 상태: {data.get('status')}")
        for c in data.get("candidates", []):
            if c.get("candidate_id") == candidate_id:
                return HandoffCandidate.model_validate(c)
        raise InvalidGenerationError(404, "candidate가 해당 generation에 없음")

    async def _fetch(self, generation_id: str) -> dict:
        url = f"{self._base_url}/api/generator/generations/{generation_id}"
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=self._transport) as client:
            for _ in range(_RETRIES + 1):
                try:
                    resp = await client.get(url)
                except httpx.HTTPError as exc:
                    last_exc = exc
                    continue
                if resp.status_code == 404:
                    raise InvalidGenerationError(404, "generation 없음")
                if resp.status_code >= 500:
                    last_exc = GeneratorUnavailableError(f"generator 5xx: {resp.status_code}")
                    continue
                if resp.status_code >= 400:
                    raise InvalidGenerationError(
                        resp.status_code, f"generator 오류: {resp.status_code}"
                    )
                return resp.json()
        raise GeneratorUnavailableError(str(last_exc) if last_exc else "generator 불통")
