# 챗 컨시어지 플랫폼 맥락 — 플랫폼 기능·페이지 맵(정적) + general 답변용 맥락 조립.
"""general(CLIO) 답변 시 시스템 프롬프트에 덧붙일 플랫폼 맥락.

거의 안 바뀌는 사실은 상수로, 가변·전문 지식은 KB(platform_guide)로 분리한다.
"""

from __future__ import annotations

# ClickMe가 제공하는 기능과 해당 페이지 — CLIO가 "무엇을 어디서 하는지" 안내할 근거.
PLATFORM_OVERVIEW = (
    "ClickMe는 광고 전주기(집행 전 예측 → 생성 → 집행·관리)를 돕는 AI 플랫폼이다. 4대 기능:\n"
    "- 광고 시뮬레이터(/simulation): OCEAN 기반 AI 가상 소비자에 광고를 테스트해 "
    "클릭의향률·구매의도·신뢰도·거부율을 분포로 예측. 상세는 /simulation/[id].\n"
    "- 광고 생성(/generator): 시뮬 결과를 반영해 개선 시안을 자동 생성·순위. "
    "상세는 /generations/[id].\n"
    "- 광고 매니지먼트(/manage): Meta 캠페인 목표·예산·성과(KPI)를 단일 창구로 관리 "
    "(모니터링·이상대응·예산·연결 하위 페이지).\n"
    "- 채팅 어시스턴트(/chat): 자유 질문 + 시뮬·생성·매니지먼트 결과 전달.\n"
    "그 외: 대시보드(/dashboard), 프로젝트(/projects), 조직·팀(/my-org·/company), 결제(/payment).\n"
    "원칙: 예측(상대 지표)과 실측(절대 지표)을 수치로 환산하지 않는다. "
    "근거가 없으면 모른다고 답한다."
)


def build_general_context(long_term: list | None = None) -> str:
    """CLIO 시스템에 덧붙일 맥락 블록 — 플랫폼 개요 + (있으면) 롱텀 메모리 요약."""
    blocks = [PLATFORM_OVERVIEW]
    items = [str(x) for x in (long_term or []) if x]
    if items:
        joined = "\n".join(f"- {m}" for m in items[:5])
        blocks.append(f"## 사용자·프로젝트 기억\n{joined}")
    return "\n\n".join(blocks)
