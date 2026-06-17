// 예산 관리 응답 타입 — 백엔드 /budget 대응

export type BudgetDecision = 'allow' | 'warn' | 'escalate' | 'block';

export type BudgetCampaignSpend = { name: string; spend_krw: number };

export type BudgetStatus = {
  tenant_id: string;
  limit_krw: number;
  spent_krw: number;
  remaining_krw: number;
  ratio: number; // 0~ (1 초과 가능)
  decision: BudgetDecision;
  thresholds: { warn: number; escalate: number };
  campaigns: BudgetCampaignSpend[];
};
