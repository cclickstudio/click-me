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


def load_media_behavior() -> dict[str, Any]:
    """단계2-β 미디어 행동(KISDI 기기별 평균 사용시간)."""
    return _read_json("media_behavior.json")


def load_population_age_sex() -> dict[str, Any]:
    """단계1 인구 분포. 공식 CSV(raw/population_age_sex.csv)가 있으면 우선 사용.

    지원 포맷: ① 행안부 원본(행정동×성×1세별, cp949) ② 정규화 ``age_band,sex,count``.
    둘 다 없으면 placeholder JSON.
    """
    if _POPULATION_CSV.exists():
        return _load_population_csv(_POPULATION_CSV)
    return _read_json("population_age_sex.json")


def _num(x: str) -> int:
    x = x.strip().replace(",", "")
    return int(x) if x and x.lstrip("-").isdigit() else 0


def _age_to_band(age: int) -> str:
    if age >= 70:
        return "70+"
    lo = (age // 10) * 10
    return f"{lo}-{lo + 9}"


def _read_csv_rows(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    import io

    return list(csv.reader(io.StringIO(text)))


# 행안부 원본 레이아웃 — 남 0~110세(col 8~118), 여 0~110세(col 119~229).
_MALE_COLS = range(8, 119)
_FEMALE_COLS = range(119, 230)


def _load_population_csv(path: Path) -> dict[str, Any]:
    rows = _read_csv_rows(path)
    header = [h.strip().lower() for h in rows[0]] if rows else []
    bands: dict[str, dict[str, int]] = {}

    if {"age_band", "sex", "count"} <= set(header):  # ② 정규화 포맷
        i_band, i_sex, i_cnt = header.index("age_band"), header.index("sex"), header.index("count")
        for r in rows[1:]:
            band, sex = r[i_band].strip(), r[i_sex].strip().upper()
            bands.setdefault(band, {"M": 0, "F": 0})[sex] += _num(r[i_cnt])
        source = f"{path.name} (정규화)"
    else:  # ① 행안부 원본 — 성×1세별을 연령밴드로 집계
        for r in rows[1:]:
            if len(r) < 230:
                continue
            for sex, cols in (("M", _MALE_COLS), ("F", _FEMALE_COLS)):
                for age, col in enumerate(cols):
                    cnt = _num(r[col])
                    if cnt:
                        bands.setdefault(_age_to_band(age), {"M": 0, "F": 0})[sex] += cnt
        ref = rows[1][1].strip() if len(rows) > 1 and len(rows[1]) > 1 else ""
        source = f"행안부 주민등록 {ref} ({path.name})"

    total = sum(mf["M"] + mf["F"] for mf in bands.values()) or 1
    out = [
        {
            "age_band": band,
            "share": round((bands[band]["M"] + bands[band]["F"]) / total, 6),
            "male_ratio": round(bands[band]["M"] / (bands[band]["M"] + bands[band]["F"]), 6)
            if (bands[band]["M"] + bands[band]["F"])
            else 0.0,
        }
        for band in sorted(bands, key=lambda b: int(b.split("-")[0].rstrip("+")))
    ]
    return {"is_placeholder": False, "source": source, "bands": out}


def data_status() -> dict[str, str]:
    """각 분포의 grounding 상태 — real / placeholder / pending(사용자 수집 필요)."""
    ocean = load_ocean_age_bands()
    population = load_population_age_sex()
    return {
        "population_age_sex": "placeholder" if population.get("is_placeholder") else "real",
        "ocean_age_bands": "real(논문 5유형 클러스터) / pending(유형비율·정확 mean·sd)"
        if ocean.get("type_proportions", {}).get("needs_real_values")
        else "real",
        "consumption_values": "real(인용)",
        "media_behavior": "real(KISDI 기기별 사용시간) / pending(시간대·성연령 교차)",
        "social_values_deep": "pending(MDIS 사회조사 raw 수동 다운로드)",
    }
