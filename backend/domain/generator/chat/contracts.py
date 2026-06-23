# 생성 채팅 슬롯 — 대화에서 모아야 하는 생성 파라미터
"""CREATE 모드 필수 슬롯과 선택 슬롯. start_generation 입력(GenerationCreateRequest)으로 매핑된다."""

from __future__ import annotations

from pydantic import BaseModel

# CREATE 모드에서 반드시 채워야 하는 슬롯(GenerationCreateRequest 검증과 일치).
REQUIRED_SLOTS: tuple[str, ...] = ("product_name", "product_description", "target_audience")

# 슬롯별 되묻기 문구(콜론 없이).
SLOT_PROMPTS: dict[str, str] = {
    "product_name": "어떤 상품·서비스 광고인가요 (상품명)",
    "product_description": "상품의 핵심 특징·장점을 한두 줄로 알려주세요",
    "target_audience": "타깃 고객은 누구인가요 (예시 — 20대 여성)",
}


class ExtractedSlots(BaseModel):
    """LLM이 대화에서 추출한 생성 슬롯. 미언급 필드는 빈 문자열로 둔다(추정 금지)."""

    product_name: str = ""
    product_description: str = ""
    target_audience: str = ""
    campaign_objective: str = ""  # conversion | awareness | traffic 등 언급 시
    format: str = ""  # single | carousel 언급 시
    project_hint: str = ""  # 사용자가 지목한 프로젝트 이름/번호
