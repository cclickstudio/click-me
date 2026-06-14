# KISDI 한국미디어패널 다이어리 raw → 연령×성별 미디어행동·노출맥락 분포 빌드(LLM✗)
#
# raw/d25v32_row_KMP_csv.csv(2024 25차, 8,411명, 3일×96슬롯·15분)에서
#   ① device_minutes — 셀별 매체대분류 일일 평균 사용시간(분)
#   ② exposure       — 셀별 (시간대·매체·행위·장소) 상위 노출맥락(가중)
# 을 계산해 distributions/media_behavior.json 으로 저장한다. d25wt 가중치 적용.
# raw 는 gitignore(커밋✗) → 집계 JSON만 커밋. 재생성: uv run python -m \
#   domain.simulation.data.simulation.build_media_behavior
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_RAW = _DIR / "raw" / "d25v32_row_KMP_csv.csv"
_OUT = _DIR / "distributions" / "media_behavior.json"

SLOT_MINUTES = 15  # 슬롯 1개 = 15분, 슬롯1 = 00:00 (저녁20~22시 피크·새벽3~4시 트로프로 확정)
_DAYS = (1, 2, 3)  # 다이어리 3일

# d25age 연령군 코드 → 밴드(ocean_age_bands.json·sampler와 정합)
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

# 매체(MA) 코드 → 대분류. 0=미이용 제외. (D_codebook 매체 시트 기준)
_MEDIUM_GROUPS: dict[str, tuple[int, ...]] = {
    "신문/잡지/책": (1,),
    "사진/편지": (2,),
    "TV": (3, 4, 5, 6),
    "PC": (7, 8, 9, 10, 11),
    "내비/키오스크": (12, 13),
    "전화기(고정)": (14, 15, 16),
    "스마트폰/휴대폰": (17, 18, 19),
    "카메라/캠코더": (20, 21),
    "라디오/오디오": (22, 23, 24, 25, 26),
    "비디오재생": (27, 28, 29, 30),
    "게임기": (31, 32),
    "문화시설": (33, 34, 35, 36, 37, 38, 39),
    "차량/기타기기": (40,),
    "XR": (41, 42, 43),
}
# 행위(AA) 코드 → 대분류
_ACTIVITY_GROUPS: dict[str, tuple[int, ...]] = {
    "TV/방송시청": (1, 2, 3, 4, 5, 29, 37, 38),
    "라디오/음악": (6, 7, 11),
    "동영상/개인방송": (8, 9, 10, 41, 42),
    "읽기": (12, 13, 14, 15, 26, 27, 28),
    "커뮤니케이션": (16, 17, 18, 19, 43, 44, 45, 46),
    "정보검색": (20,),
    "SNS": (21,),
    "쇼핑/금융": (22,),
    "게임": (23, 32),
    "문서/그래픽작업": (24, 25, 47),
    "문화/여가시설": (30, 31, 33, 34, 35, 36),
    "기기제어/기타": (39, 40),
}
# 장소(p) 코드 → 대분류
_PLACE_GROUPS: dict[str, tuple[int, ...]] = {
    "집": (1, 5),
    "타인집": (2,),
    "직장": (3,),
    "교육시설": (4,),
    "이동중": (6, 7, 8),
    "여가/외식": (9, 10, 11, 12, 15, 17),
    "상업/종교/기타": (13, 14, 16),
}

_TIMEBANDS = {"새벽": (0, 6), "오전": (6, 12), "오후": (12, 18), "저녁": (18, 24)}
_EXPOSURE_TOP_N = 15  # 셀별 상위 노출맥락 개수


def _invert(groups: dict[str, tuple[int, ...]]) -> dict[int, str]:
    return {code: name for name, codes in groups.items() for code in codes}


_MEDIUM_OF = _invert(_MEDIUM_GROUPS)
_ACTIVITY_OF = _invert(_ACTIVITY_GROUPS)
_PLACE_OF = _invert(_PLACE_GROUPS)


def _timeband(slot_1based: int) -> str:
    hour = ((slot_1based - 1) * SLOT_MINUTES // 60) % 24
    for name, (lo, hi) in _TIMEBANDS.items():
        if lo <= hour < hi:
            return name
    return "저녁"


def _to_int(x: str) -> int | None:
    x = x.strip()
    return int(x) if x.lstrip("-").isdigit() else None


def _read_rows(path: Path) -> Iterator[tuple[list[str], dict[str, int]]]:
    with path.open("rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    idx = {c: i for i, c in enumerate(header)}
    for row in reader:
        yield row, idx


def build() -> dict:
    # 셀별 누적기
    dev_min: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    dev_wsum: dict[str, float] = defaultdict(float)  # device_minutes 가중치 합(셀)
    daily_sum: dict[str, float] = defaultdict(float)
    daily_sq: dict[str, float] = defaultdict(float)
    cell_n: dict[str, int] = defaultdict(int)
    expo: dict[str, dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
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

        person_dev: dict[str, float] = defaultdict(float)  # 매체대분류별 슬롯수(3일 합)
        valid_days = 0  # 다이어리 기록이 있는 날(d25_Ndd 존재) — 미디어 미이용일도 분모 포함
        media_slots = 0  # MA≠0 슬롯수(3일 합)
        for d in _DAYS:
            dd = row[idx[f"d25_{d}dd"]].strip() if f"d25_{d}dd" in idx else ""
            if not dd:
                continue
            valid_days += 1
            for s in range(1, 97):
                ma = _to_int(row[idx[f"d25_{d}MA{s}"]])
                if ma is None or ma == 0:
                    continue
                media_slots += 1
                grp = _MEDIUM_OF.get(ma)
                if grp:
                    person_dev[grp] += 1
                # 노출맥락 — MA≠0 슬롯만
                aa = _to_int(row[idx[f"d25_{d}AA{s}"]])
                pl = _to_int(row[idx[f"d25_{d}p{s}"]])
                key = (
                    _timeband(s),
                    grp or "기타",
                    _ACTIVITY_OF.get(aa, "기타") if aa else "기타",
                    _PLACE_OF.get(pl, "기타") if pl else "기타",
                )
                expo[cell][key] += w
        if valid_days == 0:
            continue
        # 일일 환산(분) = 슬롯수 × 15 / 유효일수
        daily = media_slots * SLOT_MINUTES / valid_days
        daily_sum[cell] += w * daily
        daily_sq[cell] += w * daily * daily
        dev_wsum[cell] += w
        for grp, slots in person_dev.items():
            dev_min[cell][grp] += w * (slots * SLOT_MINUTES / valid_days)

    # 셀 → 최종 분포
    cells: dict[str, dict] = {}
    for cell in sorted(cell_n):
        wsum = dev_wsum[cell] or 1.0
        mean = daily_sum[cell] / wsum
        var = max(0.0, daily_sq[cell] / wsum - mean * mean)
        device = {
            g: round(v / wsum, 1) for g, v in sorted(dev_min[cell].items(), key=lambda kv: -kv[1])
        }
        # 노출맥락 상위 N + 재정규화
        items = sorted(expo[cell].items(), key=lambda kv: -kv[1])[:_EXPOSURE_TOP_N]
        tot = sum(v for _, v in items) or 1.0
        exposure = [
            {
                "timeband": tb,
                "medium": md,
                "activity": ac,
                "place": pl,
                "p": round(v / tot, 4),
            }
            for (tb, md, ac, pl), v in items
        ]
        cells[cell] = {
            "n": cell_n[cell],
            "daily_media_minutes": {"mean": round(mean, 1), "sd": round(var**0.5, 1)},
            "device_minutes": device,
            "exposure": exposure,
        }

    return {
        "_role": "단계2-β 미디어행동 — 연령×성별 셀별 매체 사용시간 + 노출맥락(4-b exposure).",
        "source": "KISDI 한국미디어패널 2024 raw(d25v32), 3일 다이어리×96슬롯(15분), d25wt 가중",
        "license": "공공·연구 이용",
        "is_placeholder": False,
        "slot_minutes": SLOT_MINUTES,
        "slot_start_hour": 0,
        "n_respondents": n_total,
        "timebands": {k: list(v) for k, v in _TIMEBANDS.items()},
        "medium_groups": list(_MEDIUM_GROUPS),
        "cells": cells,
    }


def main() -> None:
    data = build()
    _OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n_cells = len(data["cells"])
    print(f"저장: {_OUT.name} — {data['n_respondents']}명, {n_cells}개 셀")
    for cell, c in list(data["cells"].items()):
        top = c["device_minutes"]
        first = next(iter(top.items())) if top else ("-", 0)
        print(
            f"  {cell:>9} n={c['n']:>4} "
            f"일일{c['daily_media_minutes']['mean']:>6.0f}분 "
            f"주매체={first[0]}({first[1]}분) 노출맥락={len(c['exposure'])}"
        )


if __name__ == "__main__":
    main()
