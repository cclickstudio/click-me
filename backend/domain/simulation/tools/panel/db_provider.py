# DB 기반 고정 패널 조회(§3.6) — panels/personas 테이블을 읽기만, 없으면 폴백에 위임
#
# 로컬 JSON 캐시(CachedPanelProvider)와 동일한 get_or_build 시그니처. DB가 진짜 소스가
# 되도록(쓰기 경로는 PanelRepository.create가 이미 담당), 요청 경로 안에서 신규 빌드는 하지
# 않는다 — 미스 시 폴백(라이브 샘플러 등)에 그대로 위임해 레이턴시를 늘리지 않는다.
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from domain.simulation.contracts.schemas import PanelSpec, Persona
from domain.simulation.repositories.panel_repository import PanelRepository
from domain.simulation.tools.panel.builder import filter_personas, subset_for_spec


class DbPanelProvider:
    """DB(panels/personas)를 우선 조회하고, 없으면 fallback provider에 위임한다."""

    def __init__(self, session_factory: async_sessionmaker, *, fallback) -> None:
        self._session_factory = session_factory
        self._fallback = fallback

    async def get_or_build(self, spec: PanelSpec) -> tuple[str, list[Persona]]:
        async with self._session_factory() as session:
            found = await PanelRepository(session).get_by_version(spec.version)
        if found is None:
            return await self._fallback.get_or_build(spec)
        _, personas = found
        selected = filter_personas(personas, spec.target_filter)
        return spec.version, subset_for_spec(selected, spec.size, spec.seed)
