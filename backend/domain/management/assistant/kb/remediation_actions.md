# 조치(액션)·승인 — 증상별 권고와 실행 경로

## 행동은 제안, 실행은 승인 경로
어시스턴트는 조치를 **추천(제안)** 만 한다. 실제 실행은 제안(ActionProposal)→승인(approval)→실행기(executor)의 단일 경로로, Tier에 따라 사람 승인을 거친다. 자동승인 한도는 Tier 1까지이고, Tier 3은 항상 사람이 건별 승인한다.

## 액션 타입과 Tier
- PAUSE_CAMPAIGN(게재 중단) — Tier 1(낮은 위험).
- DECREASE_BUDGET(예산 감액) — Tier 1.
- INCREASE_BUDGET(예산 증액) — Tier 3(사람 승인).
- REPLACE_CREATIVE(소재 교체) — Tier 3.
- ACTIVATE_CAMPAIGN(게재 시작, 실과금) — Tier 3, 항상 사람 승인. 게재 시작 시 충전액을 spend_cap(평생 지출 상한)으로 걸어 그만큼만 집행되게 한다.
- CREATE_CAMPAIGN / EXPAND_AUDIENCE / CHANGE_BID_STRATEGY — Tier 3.

## 증상 → 권고 조치
- 정책 거절(WITH_ISSUES/DISAPPROVED): 소재·문구·도착지 수정 후 재심사, 반복되면 REPLACE_CREATIVE. 예산·입찰 조정으로는 해결 안 됨.
- 낮은 CTR가 지속: 소재 교체(REPLACE_CREATIVE)·타깃 조정 우선. 증액(INCREASE_BUDGET)은 효율 확인 후.
- 높은 빈도(피로): 타깃 확장(EXPAND_AUDIENCE)·소재 교체.
- 목표 ROAS 미달(목표의 70% 미만, PERFORMANCE_BELOW_TARGET): 소재 교체 우선, 그 다음 타깃·입찰(CHANGE_BID_STRATEGY).
- 월 예산 페이스 초과(런레이트 > 목표): 일예산 하향(DECREASE_BUDGET)·일부 캠페인 일시중지(PAUSE_CAMPAIGN).
- 성과 좋은데 예산 여유: INCREASE_BUDGET 검토(Tier 3 승인).

## 안전 원칙
- 게재·증액 등 돈이 늘어나는 조치는 항상 사람 승인(Tier 3). 멱등키로 중복 실행 차단.
- 예측(상대 지표)만 보고 실행을 단정하지 않는다 — 실측과 함께 판단.
