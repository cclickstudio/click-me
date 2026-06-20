# 🅱 감사 로그 마스킹 — 예산·소재·토큰 + 중첩 list 재귀 (게이트 #8·CLAUDE.md 보안)
"""mask_sensitive 회귀 테스트.

코드리뷰 2026-06-17: 예산(amount_krw)·소재(creative_id)가 평문 저장되고, list 안
중첩 dict의 민감키가 마스킹되지 않던 버그를 막는다.
"""

from domain.management.execution.audit_log import MASKED, mask_sensitive


def test_mask_sensitive_masks_budget_creative_token_and_nested_lists():
    payload = {
        "amount_krw": 50_000,
        "creative_id": "cre-1",
        "access_token": "EAA-secret",
        "targets": [{"response": {"daily_budget": 30_000, "token": "x"}}],
        "ok": "keep",
    }

    out = mask_sensitive(payload)

    assert out["amount_krw"] == MASKED  # 예산
    assert out["creative_id"] == MASKED  # 소재
    assert out["access_token"] == MASKED  # 토큰
    # list 안 중첩 dict까지 재귀 마스킹
    assert out["targets"][0]["response"]["daily_budget"] == MASKED
    assert out["targets"][0]["response"]["token"] == MASKED
    assert out["ok"] == "keep"  # 비민감 값은 보존
