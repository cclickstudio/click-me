# 패널 빌드 CLI — 기본 패널 v1(고정 시드) 1회 빌드 후 캐시 저장
#
# 사용: cd backend && uv run python -m domain.simulation.tools.panel.build_cli --size 1000 --seed 0
# GEMINI_API_KEY 필요 — 실 Gemini 서사(mock 제거). DATABASE_URL 설정 시 DB(panels/personas,
# §3.6)에도 저장 — wiring.DbPanelProvider가 이후 모든 런에서 이 베이스를 읽는다(2026-07-02).
from __future__ import annotations

import argparse
import asyncio

from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.contracts.schemas import Persona as PersonaContract
from domain.simulation.tools.panel.builder import PanelBuilder, save_panel
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler


async def _save_to_db(panel: dict) -> bool:
    """DATABASE_URL 설정 시 panels/personas 테이블에 저장. 미설정이면 스킵(False)."""
    try:
        from core.config import settings
    except Exception:  # noqa: BLE001 — .env 미구성 등 설정 자체가 안 되는 환경(스킵)
        return False

    if not getattr(settings, "database_url", None):
        return False
    from core.db import AsyncSessionLocal
    from domain.simulation.repositories.panel_repository import PanelRepository

    personas = [PersonaContract(**d) for d in panel["personas"]]
    async with AsyncSessionLocal() as session:
        await PanelRepository(session).create(
            version=panel["version"],
            seed=panel["seed"],
            size=panel["size"],
            model_version=panel["narrator"],
            grounding_meta={"dropped_qa": panel["dropped_qa"], "built_at": panel["built_at"]},
            personas=personas,
        )
        await session.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="고정 패널 빌드")
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--version", default="panel-v1")
    args = parser.parse_args()

    from domain.simulation.adapters.gemini_narrator import GeminiNarrator

    narrator = GeminiNarrator()

    # Meta 전용 — 런타임 wiring과 동일하게 도달 분포 기반 추출(§Tier2-A). 패널·런 정합 필수.
    builder = PanelBuilder(sampler=PersonaSampler(reachability_sampling=True), narrator=narrator)
    spec = PanelSpec(version=args.version, size=args.size, seed=args.seed)
    panel = builder.build(spec)
    path = save_panel(panel)
    saved_to_db = asyncio.run(_save_to_db(panel))
    print(
        f"패널 빌드 완료: {panel['size']}/{panel['requested_size']}명 "
        f"(QA 제거 {panel['dropped_qa']}), narrator={panel['narrator']} → {path}"
        f" (DB {'저장됨' if saved_to_db else '스킵 — DATABASE_URL 미설정'})"
    )


if __name__ == "__main__":
    main()
