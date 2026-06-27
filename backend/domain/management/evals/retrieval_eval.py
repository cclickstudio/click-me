# KB 하이브리드 검색 관련도 베이스라인 — Hit@k·MRR·섹션 일치율 (리랭커/CRAG 필요성 판정용).
"""대표 질문 → 기대 출처/섹션 매핑으로 현재 리트리버 품질을 측정한다.

실행: cd backend && uv run python -m domain.management.evals.retrieval_eval
판정: Hit@1·섹션일치가 높으면(예: 17청크에서 거의 1.0) 리랭커/CRAG-검색은 과투자다.
"""

from __future__ import annotations

import asyncio

from core.config import settings
from domain.management.assistant.retriever import KbRetriever

# (질문, 기대 출처, 기대 섹션 제목 부분문자열) — 4문서 섹션을 고루 덮는 측정셋(패러프레이즈 포함)
CASES: list[tuple[str, str, str]] = [
    # meta_ad_policy.md
    ("광고 심사 PENDING_REVIEW는 무슨 뜻이야", "meta_ad_policy.md", "심사 상태"),
    ("심사 중인데 노출이 0이야 정상이야", "meta_ad_policy.md", "심사 상태"),
    ("광고가 거절됐는데 어떻게 대응해야 해", "meta_ad_policy.md", "거절 사유"),
    ("WITH_ISSUES가 뜨면 뭘 확인해야 해", "meta_ad_policy.md", "복구 절차"),
    ("정책 거절은 예산을 올리면 풀려", "meta_ad_policy.md", "복구 절차"),
    ("게재 불가랑 정책 거절은 다른 거야", "meta_ad_policy.md", "게재 불가"),
    # optimization_playbook.md
    ("CTR이 낮을 때 뭘 점검해야 해", "optimization_playbook.md", "낮은 CTR"),
    ("낮은 CTR이 계속되면 어떻게 해", "optimization_playbook.md", "낮은 CTR"),
    ("빈도가 너무 높아서 피로한 것 같아", "optimization_playbook.md", "높은 빈도"),
    ("CPM이 자꾸 오르는데 왜 그래", "optimization_playbook.md", "높은 빈도"),
    ("ROAS가 목표보다 낮으면 어떻게 해", "optimization_playbook.md", "ROAS"),
    ("전환이 안 나오면 뭐부터 점검해", "optimization_playbook.md", "ROAS"),
    ("예산이 너무 빨리 소진돼", "optimization_playbook.md", "예산 페이싱"),
    ("학습 단계가 뭐야", "optimization_playbook.md", "학습 단계"),
    ("광고를 자주 수정해도 괜찮아", "optimization_playbook.md", "학습 단계"),
    # kpi_measurement_rules.md
    ("예측 CTR을 실제 CTR로 환산해도 돼", "kpi_measurement_rules.md", "스케일"),
    ("예측을 실제 성과라고 단정해도 돼", "kpi_measurement_rules.md", "정직성"),
    ("구매의도는 어떻게 측정해", "kpi_measurement_rules.md", "구매의도"),
    ("평균 점수만 보고 판단해도 돼", "kpi_measurement_rules.md", "구매의도"),
    ("시뮬레이터 4대 KPI가 뭐야", "kpi_measurement_rules.md", "4대 KPI"),
    ("클릭 의향률이 뭐야", "kpi_measurement_rules.md", "4대 KPI"),
    ("거부율은 어떻게 해석해", "kpi_measurement_rules.md", "4대 KPI"),
    # remediation_actions.md
    ("조치를 바로 실행해도 돼", "remediation_actions.md", "승인"),
    ("예산 증액은 바로 가능해 승인이 필요해", "remediation_actions.md", "Tier"),
    ("위험한 변경은 어떻게 처리돼", "remediation_actions.md", "안전"),
    ("증상별 권고 조치 알려줘", "remediation_actions.md", "증상"),
    ("성과 좋은 캠페인은 어떤 조치를 해", "remediation_actions.md", "증상"),
]


async def run(k: int = 3) -> dict:
    r = KbRetriever(api_key=settings.openai_api_key)
    hit1 = hit_k = sec1 = 0
    mrr = 0.0
    n = len(CASES)
    print(f"=== 검색 관련도 베이스라인 (n={n}, k={k}) ===")
    for q, src, sec in CASES:
        res = await r.search(q, k=k)
        sources = [c["source"] for c in res]
        top = res[0] if res else {}
        is_hit1 = bool(res) and sources[0] == src
        is_hitk = src in sources
        is_sec1 = bool(res) and top.get("source") == src and sec in (top.get("title") or "")
        rank = sources.index(src) + 1 if is_hitk else 0
        hit1 += is_hit1
        hit_k += is_hitk
        sec1 += is_sec1
        mrr += (1.0 / rank) if rank else 0.0
        mark = "✓" if is_hit1 else ("·" if is_hitk else "✗")
        print(f"  {mark} {q[:24]:26s} → top={top.get('title', 'NONE')[:18]:20s} (기대 {src})")
    out = {
        "n": n,
        "hit@1": round(hit1 / n, 3),
        f"hit@{k}": round(hit_k / n, 3),
        "section@1": round(sec1 / n, 3),
        "mrr": round(mrr / n, 3),
    }
    print(
        f"\n  Hit@1={out['hit@1']}  Hit@{k}={out[f'hit@{k}']}  "
        f"Section@1={out['section@1']}  MRR={out['mrr']}"
    )
    return out


if __name__ == "__main__":
    asyncio.run(run())
