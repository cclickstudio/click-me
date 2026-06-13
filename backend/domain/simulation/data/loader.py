# 분포 데이터 로더 — 통계 샘플링용 분포 JSON/CSV 를 읽는다 (LLM✗, 단계1~3 입력)
#
# 인구는 raw/population_age_sex.csv(공식)가 있으면 우선, 없으면 placeholder JSON 사용.
# data_status()로 무엇이 실데이터/placeholder/미확보인지 투명하게 보고(리포트 grounding 주석용).
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent
_DIST_DIR = _DATA_DIR / "distributions"
_RAW_DIR = _DATA_DIR / "raw"

_POPULATION_CSV = _RAW_DIR / "population_age_sex.csv"


def _read_json(name: str) -> dict[str, Any]:
    with (_DIST_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


def load_consumption_values() -> dict[str, Any]:
    """단계3 소비가치 응답률(속성 보유 확률)."""
    return _read_json("consumption_values.json")


def load_ocean_age_bands() -> dict[str, Any]:
    """단계2-α 성격 분포(연령밴드별 표본수·티어·5유형·트레이트 파라미터)."""
    return _read_json("ocean_age_bands.json")


def load_population_age_sex() -> dict[str, Any]:
    """단계1 인구 분포. 공식 CSV(raw/population_age_sex.csv)가 있으면 우선 사용.

    CSV 형식: 헤더 ``age_band,sex,count`` (sex 는 M/F). 없으면 placeholder JSON.
    """
    if _POPULATION_CSV.exists():
        return _load_population_csv(_POPULATION_CSV)
    return _read_json("population_age_sex.json")


def _load_population_csv(path: Path) -> dict[str, Any]:
    bands: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            band = row["age_band"].strip()
            sex = row["sex"].strip().upper()
            bands.setdefault(band, {"M": 0.0, "F": 0.0})[sex] += float(row["count"])
    total = sum(m["M"] + m["F"] for m in bands.values()) or 1.0
    out = []
    for band, mf in bands.items():
        band_total = mf["M"] + mf["F"]
        out.append(
            {
                "age_band": band,
                "share": round(band_total / total, 6),
                "male_ratio": round(mf["M"] / band_total, 6) if band_total else 0.0,
            }
        )
    return {"is_placeholder": False, "source": str(path.name), "bands": out}


def data_status() -> dict[str, str]:
    """각 분포의 grounding 상태 — real / placeholder / pending(사용자 수집 필요)."""
    ocean = load_ocean_age_bands()
    population = load_population_age_sex()
    return {
        "population_age_sex": "placeholder" if population.get("is_placeholder") else "real",
        "ocean_age_bands": "real(표본수·티어) / pending(트레이트 mean·sd)"
        if ocean["trait_params"].get("needs_real_values")
        else "real",
        "consumption_values": "real(인용)",
        "media_behavior": "pending(KISDI raw 수동 다운로드)",
        "social_values_deep": "pending(MDIS 사회조사 raw 수동 다운로드)",
    }
