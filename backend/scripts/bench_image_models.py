# 이미지 생성 모델 비교 벤치 — gpt-image-1 vs gemini-2.5-flash-image (생성/컴포즈 모드)
#
# 같은 워크로드로 양쪽 모델을 돌려 latency·생성 장수를 측정하고 결과 이미지를 저장한다.
# 프로덕션 기본값은 안 건드리고 in-process로 settings만 잠깐 바꿔 호출 → 되돌릴 코드 없음.
# 장당 비용은 빌링 콘솔 금액 차 ÷ 생성 장수로 별도 산출(context-notes-image-bench.md 참고).
#
#   cd backend && uv run python scripts/bench_image_models.py
#   cd backend && uv run python scripts/bench_image_models.py --mode gen     # 생성만
# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings
from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.pipeline.image_generator import generate_image

OUT = Path(__file__).resolve().parents[1] / "scripts/bench_out"


# ── 비교 대상 모델 (provider × 모델명) ────────────────────────────────────────
@dataclass(frozen=True)
class ModelSpec:
    label: str
    provider: str  # settings.generator_image_provider 값
    model: str  # settings.generator_image_model 값


MODELS: list[ModelSpec] = [
    ModelSpec("gpt-image-1", "openai", "gpt-image-1"),
    ModelSpec("gemini-2.5-flash-image", "google_genai", "gemini-2.5-flash-image"),
]


# ── 고정 테스트 입력 세트 (워크로드 동일성 = 공정 비교의 전제) ────────────────
@dataclass(frozen=True)
class Case:
    name: str
    product: ProductAnalysis
    strategy: AdStrategy
    template: TemplateType
    size: AdSize = AdSize.SQUARE
    brand_color: str | None = None
    tone: str | None = None


CASES: list[Case] = [
    Case(
        name="coffee_benefit_A",
        product=ProductAnalysis(
            product_name="콜드브루 원액 스틱",
            core_values=["간편함", "깊은 풍미", "휴대성"],
            pain_points=["아침마다 커피 내릴 시간이 없다"],
            benefits=["물에 타기만 하면 끝", "사무실에서도 카페 맛"],
            target_audience="20-30대 직장인",
            objective="신제품 인지도 향상",
        ),
        strategy=AdStrategy.BENEFIT,
        template=TemplateType.A,
        brand_color="#3B2A1A",
        tone="깔끔하고 신뢰감 있게",
    ),
    Case(
        name="skincare_emotional_C",
        product=ProductAnalysis(
            product_name="수분 진정 세럼",
            core_values=["저자극", "비건", "차분함"],
            pain_points=["환절기 피부 당김과 붉어짐"],
            benefits=["바르는 순간 진정", "끈적임 없는 마무리"],
            target_audience="민감성 피부 2030 여성",
            objective="브랜드 감성 각인",
        ),
        strategy=AdStrategy.EMOTIONAL,
        template=TemplateType.C,
        brand_color="#7BA6A1",
        tone="잔잔하고 고급스럽게",
    ),
]


@dataclass
class RunResult:
    model: str
    mode: str
    case: str
    latency_s: float
    ok: bool
    note: str = ""


@dataclass
class _SettingsSnapshot:
    """변경한 settings 값을 실험 후 원복하기 위한 스냅샷."""

    provider: str
    model: str
    fields: dict = field(default_factory=dict)


def _apply_model(spec: ModelSpec) -> _SettingsSnapshot:
    snap = _SettingsSnapshot(
        provider=settings.generator_image_provider,
        model=settings.generator_image_model,
    )
    settings.generator_image_provider = spec.provider
    settings.generator_image_model = spec.model
    return snap


def _restore(snap: _SettingsSnapshot) -> None:
    settings.generator_image_provider = snap.provider
    settings.generator_image_model = snap.model


async def _run_gen(spec: ModelSpec, case: Case) -> RunResult:
    """생성 모드 — 상품 이미지 없이 처음부터 배경 생성."""
    out_dir = OUT / spec.label / "gen"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    try:
        image_bytes = await generate_image(
            product_analysis=case.product,
            strategy=case.strategy,
            template=case.template,
            size=case.size,
            brand_color=case.brand_color,
            tone=case.tone,
        )
        dt = time.perf_counter() - t0
        (out_dir / f"{case.name}.png").write_bytes(image_bytes)
        return RunResult(spec.label, "gen", case.name, dt, ok=True)
    except Exception as exc:  # 벤치는 실패해도 다음 케이스 진행
        dt = time.perf_counter() - t0
        return RunResult(spec.label, "gen", case.name, dt, ok=False, note=repr(exc))


async def run_bench(mode: str) -> list[RunResult]:
    results: list[RunResult] = []
    for spec in MODELS:
        if spec.provider == "google_genai" and not settings.gemini_api_key:
            print(f"[skip] {spec.label}: GEMINI_API_KEY 미설정")
            continue
        snap = _apply_model(spec)
        try:
            for case in CASES:
                if mode in ("gen", "all"):
                    r = await _run_gen(spec, case)
                    results.append(r)
                    status = "ok" if r.ok else "FAIL"
                    print(f"[{spec.label}] gen/{case.name}: {r.latency_s:.2f}s {status} {r.note}")
        finally:
            _restore(snap)
    return results


def _print_table(results: list[RunResult]) -> None:
    print("\n=== 결과 요약 (latency) ===")
    print(f"{'model':<26} {'mode':<6} {'case':<24} {'latency(s)':>10} {'ok':>4}")
    for r in results:
        print(f"{r.model:<26} {r.mode:<6} {r.case:<24} {r.latency_s:>10.2f} {str(r.ok):>4}")

    print("\n=== 모델별 평균 latency (성공 건만) ===")
    for spec in MODELS:
        oks = [r.latency_s for r in results if r.model == spec.label and r.ok]
        avg = sum(oks) / len(oks) if oks else 0.0
        print(f"{spec.label:<26} 평균 {avg:>7.2f}s  ({len(oks)}장)")
    print("\n장당 비용 = 빌링 콘솔 금액 차 ÷ 위 생성 장수 (context-notes-image-bench.md §비용)")


def main() -> None:
    parser = argparse.ArgumentParser(description="이미지 생성 모델 비교 벤치")
    parser.add_argument("--mode", choices=["gen", "compose", "all"], default="gen")
    args = parser.parse_args()

    results = asyncio.run(run_bench(args.mode))
    _print_table(results)


if __name__ == "__main__":
    main()
