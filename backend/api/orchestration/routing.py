# 의도 라우팅 — 도메인별 점수 매처를 비교해 최적 도메인 선택(1단계, 무비용·결정론)
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.orchestration import policy


class IntentMatcher(Protocol):
    domain: str

    def score(self, query: str) -> float: ...


@dataclass(frozen=True)
class KeywordMatcher:
    domain: str
    keywords: frozenset[str]

    def score(self, query: str) -> float:
        low = query.lower()
        hits = sum(1 for k in self.keywords if k in low)
        return min(hits / 3, 1.0) if hits else 0.0


@dataclass(frozen=True)
class Candidate:
    domain: str
    score: float


@dataclass(frozen=True)
class RouteDecision:
    domain: str
    score: float
    ambiguous: bool
    candidates: tuple[Candidate, ...]


class Router:
    def __init__(self, matchers: list[IntentMatcher], default: str = "clio") -> None:
        self._matchers = list(matchers)
        self._default = default

    def route(self, query: str) -> RouteDecision:
        # 점수만 키로 안정 정렬 → 동점은 등록 순서 유지(domain 문자열 비의존)
        candidates = tuple(
            sorted(
                (Candidate(m.domain, m.score(query)) for m in self._matchers),
                key=lambda c: c.score,
                reverse=True,
            )
        )
        top = candidates[0] if candidates else None
        if top is None or top.score == 0.0:
            return RouteDecision(self._default, 0.0, False, candidates)
        runner = candidates[1].score if len(candidates) > 1 else 0.0
        ambiguous = runner > 0.0 and (top.score - runner) < policy.ROUTER_AMBIGUITY_MARGIN
        return RouteDecision(top.domain, top.score, ambiguous, candidates)
