# P9 검증 데모 — 연령×광고반응 미스매치로 방향성 일치 시연(비순환).
#
# 가설: '젊은 타깃' 광고는 연령이 높을수록 거부율↑·구매의도↓ 여야 한다. 광고반응(거부·구매의도)은
# grounding 입력이 아니라 LLM 산출이므로, 이 방향이 맞으면 "입력 재현"이 아닌 의미있는 검증이다.
# 정밀 수치 일치는 목표 아님 — 방향만(전략서 §5). 순수 판정(directional_verdict)은 LLM✗ 테스트.
from __future__ import annotations

import asyncio

from domain.simulation.contracts.schemas import SimulationRunRequest

# (age_min, age_max, 대표 연령) — 연령대별 노출 셀. 20-29가 타깃, 위로 갈수록 미스매치 커짐.
_DEFAULT_BANDS = ((20, 29, 25), (30, 39, 35), (40, 49, 45), (50, 59, 55), (60, 69, 65))


def _cov_sign(xs: list[float], ys: list[float]) -> float:
    """cov(x,y) 부호 — >0이면 y가 x와 함께 증가, <0이면 감소. (정밀도 아닌 방향만)"""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))


def directional_verdict(by_band: list[dict]) -> dict:
    """연령대별 집계 리스트 → 젊은-타깃 가설 방향성 판정. LLM 없이 순수 계산(테스트 대상).

    by_band 원소: {"age_mid", "rejection_rate", "purchase_intent", "click_intent_rate", ...}.
    """
    ages = [b["age_mid"] for b in by_band]
    rej = _cov_sign(ages, [b["rejection_rate"] for b in by_band])
    pur = _cov_sign(ages, [b["purchase_intent"] for b in by_band])
    clk = _cov_sign(ages, [b["click_intent_rate"] for b in by_band])
    rejection_rises = rej > 0  # 연령↑ → 거부율↑ (젊은 타깃 가설)
    purchase_falls = pur < 0  # 연령↑ → 구매의도↓
    return {
        "rejection_rises_with_age": rejection_rises,
        "purchase_falls_with_age": purchase_falls,
        "click_falls_with_age": clk < 0,
        # 핵심 두 방향이 모두 맞으면 가설 통과(방향성 일치).
        "directional_pass": rejection_rises and purchase_falls,
    }


async def run_age_mismatch(
    ad_content: str,
    *,
    bands: tuple = _DEFAULT_BANDS,
    n_per_band: int = 8,
    use_mock: bool = True,
    seed_base: int = 0,
) -> dict:
    """젊은-타깃 광고를 연령대별로 노출해 집계 + 방향성 판정. use_mock=False면 실 Gemini."""
    from domain.simulation.wiring import build_simulation_service

    service = build_simulation_service(use_mock=use_mock)
    by_band: list[dict] = []
    for age_min, age_max, age_mid in bands:
        req = SimulationRunRequest(
            ad_id=f"VAL-{age_min}",
            ad_content=ad_content,
            sample_size=n_per_band,
            target_filter={"age_min": age_min, "age_max": age_max},
        )
        run_id = await service.start(req)
        while service._store.get_status(run_id) not in ("COMPLETED", "FAILED"):
            await asyncio.sleep(0.05)
        result = service.get_result(run_id) or {}
        agg = result.get("aggregate") or {}
        by_band.append(
            {
                "band": f"{age_min}-{age_max}",
                "age_mid": age_mid,
                "n": agg.get("payload", {}).get("qa_passed_count", 0),
                "rejection_rate": agg.get("rejection_rate", 0.0),
                "purchase_intent": agg.get("purchase_intent", 0.0),
                "click_intent_rate": agg.get("click_intent_rate", 0.0),
            }
        )
    return {"by_band": by_band, "verdict": directional_verdict(by_band)}


def _print_report(out: dict) -> None:
    print("연령대 | n | 거부율 | 구매의도 | 클릭의향")
    for b in out["by_band"]:
        print(
            f"  {b['band']:>6} | {b['n']:>2} | {b['rejection_rate']:.2f} | "
            f"{b['purchase_intent']:.2f} | {b['click_intent_rate']:.2f}"
        )
    v = out["verdict"]
    print(
        f"\n방향성: 거부율↑(연령)={v['rejection_rises_with_age']} "
        f"구매의도↓(연령)={v['purchase_falls_with_age']} → 가설통과={v['directional_pass']}"
    )


def main() -> None:
    ad = "제로 칼로리 탄산수 신제품. 20대 직장인 타깃, 다이어트·건강 강조, 편의점 단독 출시."
    out = asyncio.run(run_age_mismatch(ad, n_per_band=8, use_mock=False))
    _print_report(out)


if __name__ == "__main__":
    main()
