# Plan-then-Execute의 고정 실행 계획 — 구조화 스텝 + 변조탐지 해시(plan_hash)
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class PlanStep:
    """Plan의 한 스텝(불변).

    주의 — inputs가 MappingProxyType(해시 불가)라 PlanStep·Plan은 **해시 불가**다. set·dict 키로
    쓰지 말 것. 필요해지면 inputs를 해시 가능한 형태로 변환하는 결정을 명시적으로 한다(동등성(==)·
    plan_hash 비교로 충분).
    """

    domain: str  # "management" | "simulation" | "generator"
    action: str  # "answer" | "generate" | "simulate" | "execute" ...
    inputs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 불변성 보강 — 확정 후 inputs 변경을 막아 plan_hash 무결성 보장(읽기전용 + 사본).
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


@dataclass(frozen=True)
class Plan:
    steps: tuple[PlanStep, ...]
    plan_hash: str


def compute_plan_hash(steps: tuple[PlanStep, ...]) -> str:
    # MappingProxyType는 json 직렬화 불가 → dict()로 평탄화 후 해시.
    canonical = json.dumps(
        [{"domain": s.domain, "action": s.action, "inputs": dict(s.inputs)} for s in steps],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_plan(steps: list[PlanStep]) -> Plan:
    frozen = tuple(steps)
    return Plan(steps=frozen, plan_hash=compute_plan_hash(frozen))
