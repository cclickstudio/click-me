// 캠페인 목록·성과 대시보드 타입 — 백엔드 /campaigns 응답 대응

export type CampaignState =
  | 'draft'
  | 'under_review'
  | 'active'
  | 'active_pending_review'
  | 'paused'
  | 'ended';

export type CampaignKpi = {
  impressions: number;
  reach: number;
  spend_krw: number;
  ctr: number; // 0~1
  cpc_krw: number;
  cpm_krw: number;
  conversions: number;
  cvr: number; // 0~1 (전환/인라인 링크클릭)
  frequency: number;
  pacing_pct: number;
};

export type CampaignSummary = CampaignKpi & {
  campaign_id: string;
  name: string;
  state: CampaignState;
  daily_budget_krw: number;
};

export type CampaignDetail = {
  campaign_id: string;
  name: string;
  state: CampaignState;
  daily_budget_krw: number;
  expected: number[];
  actual: number[];
  anomaly_hours: number[];
  summary: CampaignKpi;
};

export type CampaignsResponse = { campaigns: CampaignSummary[] };
export type CampaignView = 'table' | 'cards';
