# 분석팀 정리 스키마 변환(to_analysis_payload) 테스트 — 중복 제거·평탄화·5키 고정 (LLM✗)
from __future__ import annotations

from domain.simulation.service.analysis_view import to_analysis_payload

_RAW = {
    "run_id": "run-1",
    "simulation_id": "sim-1",
    "ad": {"ID": "ad-1", "title": "신라면", "asset_url": "C:/Temp/x.png", "status": "DRAFT"},
    "ad_analysis": {
        "ad_id": "ad-1",
        "structured_analysis": {"mock": True, "ad_credibility": 70},  # 중복 → 제거 대상
        "detected_industry": "식품/라면",
        "detected_objective": "브랜딩",
        "detected_target": "대중",
        "detected_message": "깊은 맛",
        "ad_features": {"ad_credibility": 90, "brand_mentioned": True},
        "intent_mismatch": False,
        "mismatch_detail": {
            "category": {
                "declared": "음식",
                "detected": "식품/라면",
                "match": True,
                "score": 98,
                "note": "ok",
            },
            "objective": {
                "declared": "브랜딩",
                "detected": "브랜딩",
                "match": True,
                "score": 90,
                "note": "ok",
            },
            "message": {
                "declared": "신라면",
                "detected": "깊은 맛",
                "match": True,
                "score": 95,
                "note": "ok",
            },
        },
        "model_version": "gemini-x",
    },
    "simulation": {
        "ID": "run-1",
        "ad_id": "ad-1",
        "panel_id": "panel-v1",
        "sample_size": 2,
        "qa_passed_count": 2,
        "low_sample_warning": False,
        "status": "COMPLETED",
        "model_version": "gemini-x",
        "error_detail": None,
        "ad_analysis_id": None,
    },
    "personas": [
        {  # 5키 페르소나 + 빈 narrative + weight 1.0
            "persona_id": "P-0",
            "age": 17,
            "gender": "M",
            "region": "서울",
            "ocean": {"openness": 0.1},
            "media_behavior": {
                "primary_medium": "스마트폰/휴대폰",
                "meta_reach": 0.08,
                "_source": "KISDI 2024",
            },
            "consumption_values": {
                "성능": False,
                "품질": True,
                "편의": True,
                "저렴한 가격": True,
                "취향·덕질": True,
            },
            "socioeconomic": {"_source": "KISDI 2024", "income_code": 1},
            "weight": 1.0,
            "profile_narrative": "",
        },
        {  # 3키 페르소나(누락 키는 false로 채워져야) + weight≠1 + narrative 있음
            "persona_id": "P-1",
            "age": 45,
            "gender": "F",
            "region": "부산",
            "ocean": {"openness": -0.2},
            "media_behavior": {"primary_medium": "TV", "meta_reach": 0.17, "_source": "KISDI 2024"},
            "consumption_values": {"성능": True, "품질": False, "편의": True},
            "socioeconomic": {"_source": "KISDI 2024", "income_code": 5},
            "weight": 1.5,
            "profile_narrative": "40대 직장인",
        },
    ],
    "reactions": [{"persona_id": "P-0", "weight": 1.0, "purchase_intent": 3, "trust": 5}],
    "aggregate": {
        "click_intent_rate": 0.5,
        "ci_low": 0.0,
        "ci_high": 1.0,
        "purchase_intent": 3.0,
        "trust_avg": 5.0,
        "rejection_rate": 0.0,
        "variance_warning": False,
        "effective_n": 2.0,
        "payload": {"qa_passed_count": 2},
        "engine_version": "agg-2",
    },
}


def test_meta_groups_identifiers_and_source() -> None:
    out = to_analysis_payload(_RAW)
    assert out["meta"] == {
        "run_id": "run-1",
        "simulation_id": "sim-1",
        "source": "KISDI 2024",
        "model_version": "gemini-x",
    }


def test_ad_analysis_flattened_without_structured_analysis() -> None:
    aa = to_analysis_payload(_RAW)["ad_analysis"]
    assert "structured_analysis" not in aa
    assert "mismatch_detail" not in aa
    assert aa["ad_features"] == {"ad_credibility": 90, "brand_mentioned": True}
    dims = [a["dimension"] for a in aa["alignment"]]
    assert dims == ["category", "objective", "message"]
    assert aa["alignment"][0] == {
        "dimension": "category",
        "declared": "음식",
        "detected": "식품/라면",
        "match": True,
        "score": 98,
        "note": "ok",
    }


def test_personas_source_stripped_and_consumption_fixed_five_keys() -> None:
    personas = to_analysis_payload(_RAW)["personas"]
    five = {"성능", "품질", "편의", "저렴한 가격", "취향·덕질"}
    for p in personas:
        assert "_source" not in p["media_behavior"]
        assert "_source" not in p["socioeconomic"]
        assert set(p["consumption_values"].keys()) == five  # 3키 페르소나도 5키로 채움
    # 누락 키는 false
    assert personas[1]["consumption_values"]["저렴한 가격"] is False


def test_weight_and_empty_narrative_omitted() -> None:
    personas = to_analysis_payload(_RAW)["personas"]
    assert "weight" not in personas[0] and "profile_narrative" not in personas[0]  # 1.0·빈값 생략
    assert personas[1]["weight"] == 1.5 and personas[1]["profile_narrative"] == "40대 직장인"
    assert "weight" not in to_analysis_payload(_RAW)["reactions"][0]


def test_aggregate_trimmed_to_contract_fields() -> None:
    agg = to_analysis_payload(_RAW)["aggregate"]
    assert "payload" not in agg and "engine_version" not in agg
    assert set(agg.keys()) == {
        "click_intent_rate",
        "ci_low",
        "ci_high",
        "purchase_intent",
        "trust_avg",
        "rejection_rate",
        "variance_warning",
        "effective_n",
    }


def test_ad_uses_lowercase_id() -> None:
    ad = to_analysis_payload(_RAW)["ad"]
    assert ad["id"] == "ad-1" and "ID" not in ad
