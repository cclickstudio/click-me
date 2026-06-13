# 패널 빌드 CLI — 기본 패널 v1(고정 시드) 1회 빌드 후 캐시 저장
#
# 사용: cd backend && uv run python -m domain.simulation.panel.build_cli --size 1000 --seed 0
# GEMINI_API_KEY 있으면 실 Gemini 서사, 없으면 --mock 으로 MockNarrator.
from __future__ import annotations

import argparse

from domain.simulation.adapters.mock_engine import MockNarrator
from domain.simulation.contracts.schemas import PanelSpec
from domain.simulation.panel.builder import PanelBuilder, save_panel
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler


def main() -> None:
    parser = argparse.ArgumentParser(description="고정 패널 빌드")
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--version", default="panel-v1")
    parser.add_argument("--mock", action="store_true", help="MockNarrator 사용(서사 LLM 미호출)")
    args = parser.parse_args()

    if args.mock:
        narrator = MockNarrator()
    else:
        from domain.simulation.adapters.gemini_narrator import GeminiNarrator

        narrator = GeminiNarrator()

    builder = PanelBuilder(sampler=PersonaSampler(), narrator=narrator)
    spec = PanelSpec(version=args.version, size=args.size, seed=args.seed)
    panel = builder.build(spec)
    path = save_panel(panel)
    print(
        f"패널 빌드 완료: {panel['size']}/{panel['requested_size']}명 "
        f"(QA 제거 {panel['dropped_qa']}), narrator={panel['narrator']} → {path}"
    )


if __name__ == "__main__":
    main()
