// Meta 캠페인 objective → 시뮬레이터 광고 목표(AD_GOALS.value) 단일 매핑 (ODAX 6종 + 레거시 폴백)
// 공식 근거: Meta ODAX(Outcome-Driven Ad Experiences) 6종. v21(2024-10)부터 신규 생성은 OUTCOME_* 만
// 허용되나, 기존 캠페인은 레거시 objective 문자열을 반환할 수 있어 폴백을 함께 둔다.
// 재구매·단골은 대응 Meta objective가 없어(리타게팅으로 SALES/ENGAGEMENT 사용) 매핑 대상에서 제외.
export const OBJECTIVE_TO_GOAL: Record<string, string> = {
  // ODAX (현행)
  OUTCOME_AWARENESS: '관심 유도',
  OUTCOME_ENGAGEMENT: '관심 유도',
  OUTCOME_TRAFFIC: '클릭 유도',
  OUTCOME_APP_PROMOTION: '클릭 유도',
  OUTCOME_LEADS: '가입·문의 유도',
  OUTCOME_SALES: '구매 전환',
  // 레거시(pre-ODAX) — 통합된 상위 OUTCOME과 동일하게 매핑
  BRAND_AWARENESS: '관심 유도',
  REACH: '관심 유도',
  POST_ENGAGEMENT: '관심 유도',
  VIDEO_VIEWS: '관심 유도',
  LINK_CLICKS: '클릭 유도',
  APP_INSTALLS: '클릭 유도',
  LEAD_GENERATION: '가입·문의 유도',
  MESSAGES: '가입·문의 유도',
  CONVERSIONS: '구매 전환',
  PRODUCT_CATALOG_SALES: '구매 전환',
};

// Meta objective 문자열 → 광고 목표. 미지원/미상이면 null.
export function goalFromObjective(objective: string | null | undefined): string | null {
  if (!objective) return null;
  return OBJECTIVE_TO_GOAL[objective] ?? null;
}
