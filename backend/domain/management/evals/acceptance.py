"""🤝 인수 기준 문서 — PRD §9.5 완료조건 + §9.9 게이트.

실행 가능한 pytest 인수 테스트는 tests/management/test_acceptance.py 에 있다.
이 모듈은 기준을 문서화하고, 외부에서 재사용 가능한 헬퍼를 노출한다.
"""

from __future__ import annotations

#: PRD §9.5 어시스턴트 완료조건 ─────────────────────────────────────────────
ACCEPTANCE_CRITERIA = [
    "A1: 질문에 비어있지 않은 답을 반환한다",
    "A2: 반드시 하나 이상의 도구를 호출한다",
    "A3: 모든 citation.kind가 live|kb|web 중 하나다",
    "A4: 예산 질문은 live_budget 도구를 사용하고 evidence에 수치가 있다",
    "A5: 캠페인 목록 질문은 live_campaigns 도구를 사용한다",
    "A6: campaign_id 주어지면 live_campaign_detail 도구를 사용한다",
    "A7: 행동 의도는 직접 실행 없이 suggested_action으로만 제안한다",
]

#: PRD §9.9 감지→진단→승인→집행 게이트 ─────────────────────────────────────
GATE_CRITERIA = [
    "G1: 고장 주입 시 이상 구간이 감지된다",
    "G2: 이상 구간에서 진단과 제안이 생성된다",
    "G3: 신선한 제안은 유효성 검사를 통과한다",
    "G4: 승인된 액션에 approval_id가 있다",
    "G5: 만료된 제안은 유효성 검사에서 탈락한다",
]
