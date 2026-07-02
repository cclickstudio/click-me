# 채팅 순수 헬퍼 — 메모리/브랜드 컨텍스트 포맷·브랜드 출력·백그라운드 영속(orchestrator에서 이전)
"""LLM 호출 없는 순수/경량 헬퍼. 통합 에이전트 빌더·tool이 공유한다."""

from __future__ import annotations

import asyncio

from domain.chat import history


def format_ltm(ltm: list[dict]) -> str:
    """롱텀 메모리 목록 → 시스템 프롬프트에 앞붙일 컨텍스트 문자열(없으면 빈 문자열)."""
    if not ltm:
        return ""
    lines: list[str] = []
    for m in ltm:
        c = m.get("content") or {}
        if m.get("memory_type") == "sim_input":
            lines.append(
                f"- 최근 시뮬 입력: 제목 '{c.get('ad_title', '')}', "
                f"카테고리 '{c.get('product_category', '')}'"
            )
        elif m.get("memory_type") == "gen_input":
            lines.append(
                f"- 최근 생성 입력: 상품 '{c.get('product_name', '')}', "
                f"타깃 '{c.get('target_audience', '')}'"
            )
        elif m.get("memory_type") == "session_summary":
            lines.append(f"- 이전 대화 요약: {c.get('summary', '')}")
        else:
            lines.append(f"- 사용자 선호: {c}")
    return "이 프로젝트의 최근 맥락(참고용):\n" + "\n".join(lines) + "\n\n"


def format_brand(brand: dict | None) -> str:
    """브랜드 프로파일 → 시스템 프롬프트 앞 컨텍스트(없으면 빈 문자열)."""
    if not brand:
        return ""
    parts = []
    if brand.get("brand_name"):
        parts.append(f"브랜드 {brand['brand_name']}")
    if brand.get("tone"):
        parts.append(f"톤 {brand['tone']}")
    if brand.get("target_audience"):
        parts.append(f"타깃 {brand['target_audience']}")
    if brand.get("product_category"):
        parts.append(f"카테고리 {brand['product_category']}")
    if brand.get("keywords"):
        parts.append(f"키워드 {', '.join(brand['keywords'])}")
    if not parts:
        return ""
    return "이 프로젝트의 브랜드 설정(참고용): " + " · ".join(parts) + "\n\n"


def brand_show_text(brand: dict | None) -> str:
    """'브랜드 설정 보여줘' 응답 텍스트."""
    if not brand or not any(brand.get(k) for k in brand):
        return "아직 저장된 브랜드 설정이 없어요. '타겟은 20대 여성이야'처럼 알려주시면 기억할게요."
    lines = ["현재 브랜드 설정이에요."]
    labels = {
        "brand_name": "브랜드명",
        "tone": "톤",
        "target_audience": "타깃",
        "product_category": "카테고리",
        "keywords": "키워드",
    }
    for k, label in labels.items():
        v = brand.get(k)
        if v:
            lines.append(f"- {label}: {', '.join(v) if isinstance(v, list) else v}")
    return "\n".join(lines)


# 입력 위젯 표시·tool 응답을 막지 않게 ltm 저장·프로필 추론을 백그라운드로(결과는 다음 대화 반영).
_bg_tasks: set[asyncio.Task] = set()

# mem_type → (feature_type, action). 실행 히스토리(롱텀메모리) 적재용 매핑.
_FEATURE_BY_MEM = {
    "sim_input": ("simulation", "run_simulation"),
    "gen_input": ("generation", "run_generation"),
}


def spawn_persist(project_id: str | None, mem_type: str, data: dict) -> None:
    """sim_input/gen_input을 롱텀메모리·실행 히스토리 저장 + 프로필 추론(백그라운드, 실패 무시)."""
    if not project_id:
        return

    async def _run() -> None:
        try:
            await history.save_long_term_memory(project_id, mem_type, data)
            feat = _FEATURE_BY_MEM.get(mem_type)
            if feat:  # 기능 수행 이력을 BM25 키워드 서치용으로 별도 적재
                await history.record_execution(
                    project_id, feat[0], feat[1], history._memory_text(mem_type, data), payload=data
                )
            await history.infer_profile_from_execution_history(project_id)
        except Exception as exc:  # noqa: BLE001 — 영속 실패가 위젯/응답을 막지 않게
            print(f"[chat] persist error: {exc!r}")

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
