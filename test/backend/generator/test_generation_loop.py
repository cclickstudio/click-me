# 생성 자동 개선 루프 제어 검증 — start_generation/get_detail/_derive_fix 모킹으로 결정론 흐름만 테스트.
from __future__ import annotations

import pytest

import domain.generator.service.generation_loop as gl
from domain.generator.contracts.enums import GenerationMode
from domain.generator.service import generator_service


def _detail(score: float, cid: str, s3: str) -> dict:
    """quality_score를 통제한 get_detail 결과(후보 1개, 이미 랭크됨 가정)."""
    return {
        "status": "completed",
        "candidates": [
            {
                "candidate_id": cid,
                "quality_score": score,
                "s3_key": s3,
                "qa_result": {"cta_exists": {"score": 0.5}},
                "copy": {"headline": "헤드라인", "body": "본문", "cta": "지금 확인"},
                "performance_summary": f"품질 {round(score * 100)}점",
            }
        ],
    }


@pytest.fixture
def patched(monkeypatch):
    """start_generation/get_detail/_await_completion/_derive_fix를 모킹하고, 호출 캡처를 반환."""
    captured: dict = {"requests": [], "fix_for": []}
    gen_ids: list[str] = []
    details: list[dict] = []

    async def _start(request, created_by=None, **kw):  # noqa: ANN001
        captured["requests"].append(request)
        return gen_ids.pop(0)

    async def _get(generation_id, org_id=None):  # noqa: ANN001
        return details.pop(0)

    async def _noop(*a, **k):  # noqa: ANN002, ANN003
        return None

    async def _fix(candidate, seed):  # noqa: ANN001
        captured["fix_for"].append(candidate.get("candidate_id"))
        return "- CTA를 더 크게"

    monkeypatch.setattr(generator_service, "start_generation", _start)
    monkeypatch.setattr(generator_service, "get_detail", _get)
    monkeypatch.setattr(gl, "_await_completion", _noop)
    monkeypatch.setattr(gl, "_derive_fix", _fix)
    return captured, gen_ids, details


_SEED = {
    "product_name": "수분크림",
    "product_description": "24시간 보습",
    "target_audience": "20대 여성",
    "campaign_objective": "conversion",
}


async def test_meets_threshold_no_improve(patched):
    captured, gen_ids, details = patched
    gen_ids.extend(["g0"])
    details.extend([_detail(0.9, "c0", "s0")])

    result = await gl.run_generation_loop(_SEED, quality_target=0.8, max_iterations=3)

    assert result["threshold_met"] is True
    assert result["iterations"] == 0
    assert result["final_generation_id"] == "g0"
    assert len(captured["requests"]) == 1  # 개선 없이 최초 생성 1회
    assert captured["requests"][0].mode == GenerationMode.CREATE


async def test_improves_once_then_meets(patched):
    captured, gen_ids, details = patched
    gen_ids.extend(["g0", "g1"])
    details.extend([_detail(0.6, "c0", "s0"), _detail(0.85, "c1", "s1")])

    result = await gl.run_generation_loop(_SEED, quality_target=0.8, max_iterations=3)

    assert result["iterations"] == 1
    assert result["threshold_met"] is True
    assert result["final_generation_id"] == "g1"
    assert result["best_candidate"]["candidate_id"] == "c1"
    # 개선 요청은 IMPROVE 모드 + 직전 best의 s3_key + _derive_fix 결과를 실었다.
    improve_req = captured["requests"][1]
    assert improve_req.mode == GenerationMode.IMPROVE
    assert improve_req.existing_ad_s3_key == "s0"
    assert improve_req.fix_requests == "- CTA를 더 크게"
    assert captured["fix_for"] == ["c0"]


async def test_stops_at_max_iterations(patched):
    captured, gen_ids, details = patched
    gen_ids.extend(["g0", "g1", "g2"])
    details.extend([_detail(0.5, "c0", "s0"), _detail(0.5, "c1", "s1"), _detail(0.5, "c2", "s2")])

    result = await gl.run_generation_loop(_SEED, quality_target=0.9, max_iterations=2)

    assert result["iterations"] == 2  # 상한에서 중단
    assert result["threshold_met"] is False
    assert len(captured["requests"]) == 3  # create 1 + improve 2


async def test_keeps_better_across_iterations(patched):
    captured, gen_ids, details = patched
    gen_ids.extend(["g0", "g1", "g2"])
    # 0.6 → (개선 실패)0.4 → (개선)0.7. best는 0.7(g2)로 유지.
    details.extend([_detail(0.6, "c0", "s0"), _detail(0.4, "c1", "s1"), _detail(0.7, "c2", "s2")])

    result = await gl.run_generation_loop(_SEED, quality_target=0.9, max_iterations=2)

    assert result["threshold_met"] is False
    assert result["best_candidate"]["candidate_id"] == "c2"
    assert result["final_generation_id"] == "g2"
    # iter1·iter2 개선 모두 그 시점 best(0.6=c0/s0)를 기반으로 improve — iter1이 더 나빠 best 유지.
    assert captured["requests"][1].existing_ad_s3_key == "s0"
    assert captured["requests"][2].existing_ad_s3_key == "s0"
