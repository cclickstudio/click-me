# 오케스트레이션 정책 단일 출처 — 임계값·순차마커·파이프라인(하드코딩 금지, 여기서만)
from __future__ import annotations

# 복합/순차 의도 마커 — 게이트 B 진입 판정에 사용(자연어 휴리스틱).
SEQUENTIAL_MARKERS: frozenset[str] = frozenset(
    {"괜찮으면", "하고", "그다음", "그리고", "후에", "한 뒤"}
)

# 라우터 ambiguous 판정 마진 — top-runner 차가 이 값 미만이면 애매(routing.py가 읽음).
ROUTER_AMBIGUITY_MARGIN: float = 0.15

# 도메인 ↔ 단일스텝 액션 정본 매핑(양방향 단일 출처 — ACTION_TO_DOMAIN은 역매핑 자동 파생).
DOMAIN_TO_ACTION: dict[str, str] = {
    "management": "answer",
    "generator": "generate",
    "simulation": "simulate",
}
ACTION_TO_DOMAIN: dict[str, str] = {action: domain for domain, action in DOMAIN_TO_ACTION.items()}

# 멀티스텝 정규 순서 — 액션만 나열. 도메인은 ACTION_TO_DOMAIN으로 해석(쌍 중복 제거).
# S5에서 "execute" 추가.
PIPELINE_ORDER: tuple[str, ...] = ("generate", "simulate")
