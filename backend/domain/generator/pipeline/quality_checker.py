# 광고 카피를 규칙 기반으로 품질 검증하는 노드 (LLM 호출 없음)
from __future__ import annotations

from domain.generator.contracts.pipeline_schemas import AdCopy, QualityCheckItem, QualityReport


def _check_text_length(ad_copy: AdCopy) -> QualityCheckItem:
    h_ok = len(ad_copy.headline) <= 20
    b_ok = len(ad_copy.body) <= 50
    c_ok = len(ad_copy.cta) <= 10
    passed = h_ok and b_ok and c_ok
    issues = []
    if not h_ok:
        issues.append(f"헤드라인 {len(ad_copy.headline)}자 (20자 초과)")
    if not b_ok:
        issues.append(f"본문 {len(ad_copy.body)}자 (50자 초과)")
    if not c_ok:
        issues.append(f"CTA {len(ad_copy.cta)}자 (10자 초과)")
    return QualityCheckItem(
        passed=passed,
        score=round(sum([h_ok, b_ok, c_ok]) / 3, 2),
        feedback=", ".join(issues) if issues else "길이 적합",
    )


def _check_cta_exists(ad_copy: AdCopy) -> QualityCheckItem:
    passed = bool(ad_copy.cta.strip())
    return QualityCheckItem(
        passed=passed,
        score=1.0 if passed else 0.0,
        feedback="CTA 존재" if passed else "CTA 없음",
    )


def _check_duplicate(ad_copy: AdCopy) -> QualityCheckItem:
    h, b, c = ad_copy.headline.strip(), ad_copy.body.strip(), ad_copy.cta.strip()
    overlaps = []
    if h and b and (h in b or b in h):
        overlaps.append("헤드라인↔본문")
    if h and c and (h in c or c in h):
        overlaps.append("헤드라인↔CTA")
    if b and c and (b in c or c in b):
        overlaps.append("본문↔CTA")
    passed = not overlaps
    return QualityCheckItem(
        passed=passed,
        score=1.0 if passed else 0.0,
        feedback="중복 없음" if passed else f"중복 감지: {', '.join(overlaps)}",
    )


def _skipped_item() -> QualityCheckItem:
    return QualityCheckItem(passed=True, score=1.0, feedback="규칙 기반 검증 제외")


def check_quality(ad_copy: AdCopy, target: str) -> QualityReport:
    text_length = _check_text_length(ad_copy)
    cta_exists = _check_cta_exists(ad_copy)
    duplicate_check = _check_duplicate(ad_copy)

    overall_passed = text_length.passed and cta_exists.passed and duplicate_check.passed

    return QualityReport(
        typo_check=_skipped_item(),
        duplicate_check=duplicate_check,
        cta_exists=cta_exists,
        readability=_skipped_item(),
        target_fit=_skipped_item(),
        text_length=text_length,
        brand_consistency=_skipped_item(),
        overall_passed=overall_passed,
    )
