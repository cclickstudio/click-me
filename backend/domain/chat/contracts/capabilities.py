# 챗 라우팅·스코프의 단일 진실원천 — 각 서브에이전트의 역량·필수 스코프(레지스트리).
"""라우팅 프롬프트·스코프 가드가 이 dict 하나를 소비 — 텍스트/스코프 드리프트 방지.

도메인 기능이 늘면 여기만 갱신한다(라우트 정의와 실제 툴 등록의 정합 책임은 여기).
"""

from __future__ import annotations

from domain.chat.contracts.agent_io import Route

CAPABILITIES: dict[Route, dict] = {
    Route.MANAGEMENT: {
        "label": "광고 매니지먼트",
        "does": "캠페인 성과·예산·소진·집행(일시중지/증액 등)의 조회와 실행",
        "required_scopes": ["organization_id"],
        "hitl": True,
    },
    Route.SIMULATION: {
        "label": "광고 시뮬레이터",
        "does": "집행 전 반응 예측·4대 KPI·페르소나 근거, 시뮬 결과 조회",
        "required_scopes": ["project_id"],
        "hitl": False,
    },
    Route.GENERATION: {
        "label": "광고 생성",
        "does": "새 시안 생성, 그리고 내가/우리가 생성한 시안·생성물의 목록·개수·상세·상태 조회",
        "required_scopes": ["organization_id", "project_id"],
        "hitl": False,
    },
}
