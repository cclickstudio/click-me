# 분석팀 핸드오프용 출력 정리 — 내부 result dict를 중복 제거·평탄화한 분석 스키마로 변환
#
# 원본 /run 결과(프론트가 소비)는 그대로 두고, 이 presenter가 읽기 전용으로 변환만 한다.
# 바꾸는 것: structured_analysis 중복 제거, mismatch_detail+rubric → alignment[], _source 전역화,
# consumption_values 5키 고정, 빈 profile_narrative·weight=1 생략, 식별자 meta로 묶기.
from __future__ import annotations

from typing import Any

from domain.simulation.data.simulation import loader

_ALIGN_DIMS = ("category", "objective", "message")
_AGG_KEEP = (
    "click_intent_rate",
    "ci_low",
    "ci_high",
    "purchase_intent",
    "trust_avg",
    "rejection_rate",
    "variance_warning",
    "effective_n",
)


def _canonical_consumption_keys() -> list[str]:
    """소비가치 5키 = 데이터 원본 values(3) + generation_specific 하위(2). 하드코딩 회피."""
    cv = loader.load_consumption_values()
    keys = list((cv.get("values") or {}).keys())
    for gen in (cv.get("generation_specific") or {}).values():
        for k in gen:
            if k not in keys:
                keys.append(k)
    return keys


def _alignment(ad_analysis: dict) -> list[dict]:
    """mismatch_detail(차원별 declared/detected/match/score/note)로 alignment[] 조립.

    rubric_scores 는 같은 score·note 의 중복이라 사용하지 않는다(분석팀 요청).
    """
    md = ad_analysis.get("mismatch_detail") or {}
    out: list[dict] = []
    for dim in _ALIGN_DIMS:
        d = md.get(dim)
        if not d:
            continue
        out.append(
            {
                "dimension": dim,
                "declared": d.get("declared"),
                "detected": d.get("detected"),
                "match": d.get("match"),
                "score": d.get("score"),
                "note": d.get("note"),
            }
        )
    return out


def _clean_ad(ad: dict) -> dict:
    return {
        "id": ad.get("ID"),
        "project_id": ad.get("project_id"),
        "title": ad.get("title"),
        "media_type": ad.get("media_type"),
        "asset_url": ad.get("asset_url"),  # ⚠️ S3 연동 전엔 로컬/None — 인프라 작업 별도
        "copy_text": ad.get("copy_text"),
        "product_category": ad.get("product_category"),
        "ad_objective": ad.get("ad_objective"),
        "status": ad.get("status"),
    }


def _clean_ad_analysis(aa: dict) -> dict:
    return {
        "detected_industry": aa.get("detected_industry"),
        "detected_objective": aa.get("detected_objective"),
        "detected_target": aa.get("detected_target"),
        "detected_message": aa.get("detected_message"),
        "intent_mismatch": aa.get("intent_mismatch", False),
        "ad_features": aa.get("ad_features") or {},
        "alignment": _alignment(aa),
    }


def _clean_simulation(sim: dict) -> dict:
    return {
        "id": sim.get("ID"),
        "ad_id": sim.get("ad_id"),
        "panel_id": sim.get("panel_id"),
        "organization_id": sim.get("organization_id"),
        "target_mode": sim.get("target_mode"),
        "target_filter": sim.get("target_filter"),
        "sample_size": sim.get("sample_size"),
        "qa_passed_count": sim.get("qa_passed_count"),
        "low_sample_warning": sim.get("low_sample_warning"),
        "status": sim.get("status"),
    }


def _clean_persona(p: dict, consumption_keys: list[str]) -> dict:
    mb = {k: v for k, v in (p.get("media_behavior") or {}).items() if k != "_source"}
    se = {k: v for k, v in (p.get("socioeconomic") or {}).items() if k != "_source"}
    cv_in = p.get("consumption_values") or {}
    out: dict[str, Any] = {
        "persona_id": p.get("persona_id"),
        "age": p.get("age"),
        "gender": p.get("gender"),
        "region": p.get("region"),
        "ocean": p.get("ocean"),
        "media_behavior": mb,
        "consumption_values": {k: bool(cv_in.get(k, False)) for k in consumption_keys},
        "socioeconomic": se,
    }
    if p.get("weight", 1.0) != 1.0:  # 기본 1.0이면 생략
        out["weight"] = p.get("weight")
    if p.get("profile_narrative"):  # 빈 문자열이면 생략
        out["profile_narrative"] = p.get("profile_narrative")
    return out


def _clean_reaction(r: dict) -> dict:
    return {k: v for k, v in r.items() if not (k == "weight" and v == 1.0)}


def _collect_source(personas: list[dict]) -> str | None:
    for p in personas:
        for blk in (p.get("media_behavior"), p.get("socioeconomic")):
            if blk and blk.get("_source"):
                return blk["_source"]
    return None


def to_analysis_payload(result: dict) -> dict:
    """내부 result dict → 분석팀 정리 스키마(읽기 전용 변환)."""
    aa = result.get("ad_analysis") or {}
    personas = result.get("personas") or []
    ck = _canonical_consumption_keys()
    return {
        "meta": {
            "run_id": result.get("run_id"),
            "simulation_id": result.get("simulation_id"),
            "source": _collect_source(personas),
            "model_version": aa.get("model_version"),
        },
        "ad": _clean_ad(result.get("ad") or {}),
        "ad_analysis": _clean_ad_analysis(aa),
        "simulation": _clean_simulation(result.get("simulation") or {}),
        "personas": [_clean_persona(p, ck) for p in personas],
        "reactions": [_clean_reaction(r) for r in (result.get("reactions") or [])],
        "aggregate": {k: (result.get("aggregate") or {}).get(k) for k in _AGG_KEEP},
    }
