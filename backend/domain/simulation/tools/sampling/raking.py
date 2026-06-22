# 외부 marginal raking — IPF로 패널 가중치를 목표 결합 marginal에 정합(편향 보정, LLM✗)
#
# 진짜 성격×행동 joint(개인단위 연결 데이터 부재)는 다루지 않는다. 여기선 표본을 census 등 외부
# 주변분포(나이밴드·성별 등)에 맞춰 '가중치만' 재조정한다 — 추출분포는 불변, §3.7 불편추정 강화.
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def rake_weights(
    rows: list[Any],
    targets: list[tuple[Callable[[Any], Any], dict[Any, float]]],
    *,
    base_weights: list[float] | None = None,
    iterations: int = 50,
    tol: float = 1e-7,
) -> list[float]:
    """IPF(raking) — 각 row 가중치를 목표 marginal들에 정합. 가중합=행 수 정규화(평균 1.0).

    targets: (key_fn, {범주: 목표비율}) 목록. key_fn(row)이 그 row의 범주, 목표비율 합≈1.
    목표 dict에 없는 범주를 가진 row는 그 차원에서 건드리지 않는다(부분 정합 허용).
    base_weights 미지정 시 1.0에서 시작.
    """
    n = len(rows)
    if n == 0:
        return []
    w = list(base_weights) if base_weights is not None else [1.0] * n
    keys = [[kf(r) for kf, _ in targets] for r in rows]  # row별 차원별 범주(1회 산출)
    for _ in range(iterations):
        max_delta = 0.0
        for d, (_, target) in enumerate(targets):
            cur: dict[Any, float] = {}
            for i in range(n):
                cur[keys[i][d]] = cur.get(keys[i][d], 0.0) + w[i]
            total = sum(w) or 1.0
            for i in range(n):
                cat = keys[i][d]
                tgt = target.get(cat)
                if tgt is None or cur.get(cat, 0.0) <= 0.0:
                    continue
                factor = (tgt * total) / cur[cat]
                max_delta = max(max_delta, abs(factor - 1.0))
                w[i] *= factor
        if max_delta < tol:
            break
    s = sum(w) or 1.0
    return [x * n / s for x in w]
