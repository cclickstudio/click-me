# 캠페인 이름 자동 제안 — 규칙 폴백이 항상 3개 이하 비어있지 않은 후보를 주는지
from datetime import UTC, datetime

from domain.management.naming import rule_based_names, suggest_campaign_names

_NOW = datetime(2026, 7, 3, tzinfo=UTC)


def test_rule_names_full_ingredients():
    names = rule_based_names(
        title="여름 신상 원피스",
        copy_text="시원한 여름을 미리 만나보세요! 지금 주문 시 20% 할인",
        product_category="원피스",
        industry_category="패션",
        target_filter={"age_min": 25, "age_max": 34, "gender": "female"},
        objective="traffic",
        click_intent_rate=0.31,
        now=_NOW,
    )
    assert 1 <= len(names) <= 3
    assert names[0] == "원피스_2534여성_트래픽_7월"
    assert all(len(n) <= 40 for n in names)
    assert len(set(names)) == len(names)  # 중복 없음


def test_rule_names_minimal_ingredients():
    """소재 정보가 비어도 폼이 비지 않게 기본 후보가 나온다."""
    names = rule_based_names(
        title=None,
        copy_text=None,
        product_category=None,
        industry_category=None,
        target_filter=None,
        objective="leads",
        click_intent_rate=None,
        now=_NOW,
    )
    assert names
    assert all("리드" in n or n for n in names)


async def test_suggest_falls_back_without_key():
    """OpenAI 키가 없으면 LLM을 부르지 않고 규칙 후보를 그대로 반환."""
    names = await suggest_campaign_names(
        ad={"title": "테스트 광고", "copy_text": None, "target_filter": None},
        objective="traffic",
        click_intent_rate=0.5,
        openai_api_key=None,
    )
    assert names
    assert any("테스트 광고" in n for n in names)
