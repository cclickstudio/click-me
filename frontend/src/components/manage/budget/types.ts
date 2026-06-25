// 예산 관리 응답 타입 — 백엔드 /budget 대응

export type BudgetDecision = 'allow' | 'warn' | 'escalate' | 'block';

export type BudgetCampaignSpend = { name: string; spend_krw: number; roas?: number | null };

export type BudgetDayPoint = { date: string; spend_krw: number };

export type BudgetStatus = {
  tenant_id: string;
  limit_krw: number; // = 월 목표(monthly_target_krw)와 동일
  spent_krw: number; // 이번 달 실소진
  remaining_krw: number;
  ratio: number; // 0~ (1 초과 가능)
  decision: BudgetDecision;
  thresholds: { warn: number; escalate: number };
  campaigns: BudgetCampaignSpend[];
  // 페이싱 확장(live)
  monthly_target_krw?: number;
  projection_krw?: number; // 런레이트 월말 예상 소진
  account_balance_krw?: number; // Meta 선불 가용 잔액(여력=실광고비)
  account_spend_cap_krw?: number; // Meta 충전 한도(부가세 제외 집행가능액)
  account_amount_spent_krw?: number; // Meta 누적 지출
  credit_charged_krw?: number; // ClickMe 크레딧 총 충전(집행 한도)
  credit_balance_krw?: number; // ClickMe 크레딧 잔액
  period?: string; // 'YYYY-MM'
  daily?: BudgetDayPoint[];
};
