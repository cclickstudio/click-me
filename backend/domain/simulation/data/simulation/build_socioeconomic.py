# KISDI 한국미디어패널 raw → 연령×성별 소득·학력 분포 빌드(LLM✗)
#
# raw/d25v32 의 d25p_income(개인 월평균 소득 8구간 리코드)·d25school(최종학력 6단계)을
# 연령×성별 셀별 분포로 집계해 distributions/socioeconomic.json 저장. d25wt 가중.
# 구간 라벨은 KISDI 코드북 리코드 기준(코드도 함께 보존). raw는 gitignore → 집계 JSON만 커밋.
# 재생성: uv run python -m domain.simulation.data.simulation.build_socioeconomic
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_RAW = _DIR / "raw" / "d25v32_row_KMP_csv.csv"
_OUT = _DIR / "distributions" / "socioeconomic.json"

_AGE_BAND = {
    "1": "0-9",
    "2": "10-19",
    "3": "20-29",
    "4": "30-39",
    "5": "40-49",
    "6": "50-59",
    "7": "60-69",
    "8": "70+",
}
_GENDER = {"1": "M", "2": "F"}

# d25p_income 8구간 리코드(오름차순) — 라벨은 KISDI 코드북 기준, 코드는 income_code로 보존.
_INCOME_LABEL = {
    "1": "소득 없음",
    "2": "100만원 미만",
    "3": "100~200만원",
    "4": "200~300만원",
    "5": "300~400만원",
    "6": "400~500만원",
    "7": "500~800만원",
    "8": "800만원 이상",
}
# d25school 6단계 최종학력
_EDU_LABEL = {
    "1": "미취학",
    "2": "초등학교",
    "3": "중학교",
    "4": "고등학교",
    "5": "대학교",
    "6": "대학원",
}


def _read_rows(path: Path) -> Iterator[tuple[list[str], dict[str, int]]]:
    with path.open("rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    idx = {c: i for i, c in enumerate(header)}
    for row in reader:
        yield row, idx


def _dist(counter: dict[str, float], label_map: dict[str, str]) -> list[dict]:
    """코드별 가중합 → share 내림차순 리스트(라벨·코드·share)."""
    total = sum(counter.values()) or 1.0
    items = sorted(counter.items(), key=lambda kv: -kv[1])
    return [
        {"label": label_map.get(code, f"코드{code}"), "code": code, "share": round(v / total, 4)}
        for code, v in items
        if code in label_map  # 결측/무응답 코드는 분포에서 제외
    ]


def build() -> dict:
    income: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    edu: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cell_n: dict[str, int] = defaultdict(int)
    n_total = 0

    for row, idx in _read_rows(_RAW):
        band = _AGE_BAND.get(row[idx["d25age"]])
        gender = _GENDER.get(row[idx["d25gender"]])
        if not band or not gender:
            continue
        try:
            w = float(row[idx["d25wt"]].strip() or 1.0)
        except ValueError:
            w = 1.0
        cell = f"{band}|{gender}"
        n_total += 1
        cell_n[cell] += 1
        income[cell][row[idx["d25p_income"]].strip()] += w
        edu[cell][row[idx["d25school"]].strip()] += w

    cells = {
        cell: {
            "n": cell_n[cell],
            "income": _dist(income[cell], _INCOME_LABEL),
            "education": _dist(edu[cell], _EDU_LABEL),
        }
        for cell in sorted(cell_n)
    }
    return {
        "_role": "단계1 확장 — 연령×성별 소득(8구간)·학력(6단계) 분포. 구매의도 grounding 보강.",
        "source": "KISDI 한국미디어패널 2024 raw(d25v32) d25p_income·d25school, d25wt 가중",
        "license": "공공·연구 이용",
        "is_placeholder": False,
        "income_labels": _INCOME_LABEL,
        "education_labels": _EDU_LABEL,
        "n_respondents": n_total,
        "cells": cells,
    }


def main() -> None:
    data = build()
    _OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {_OUT.name} — {data['n_respondents']}명, {len(data['cells'])}개 셀")
    for cell, c in data["cells"].items():
        top_inc = c["income"][0] if c["income"] else {"label": "-", "share": 0}
        top_edu = c["education"][0] if c["education"] else {"label": "-", "share": 0}
        print(
            f"  {cell:>9} n={c['n']:>4} "
            f"주소득={top_inc['label']}({top_inc['share']}) "
            f"주학력={top_edu['label']}({top_edu['share']})"
        )


if __name__ == "__main__":
    main()
