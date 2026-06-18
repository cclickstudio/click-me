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
  conversions: number | null; // 전환 추적 미설정(픽셀/CAPI 전)이면 null
  cvr: number | null; // 0~1 (전환/인라인 링크클릭) — 미설정이면 null
  roas: number | null; // 매출÷지출 — 전환 가치 추적 전이면 null(측정 불가)
  conversion_tracking?: boolean; // 실모드에서 전환 추적 여부 (false면 cvr/conversions=null)
  frequency: number;
  pacing_pct: number;
};

// 전환 추적 미설정이면 cvr/conversions가 null — "0.0%"로 거짓표시 금지, "미설정"으로 표기.
export const fmtCvr = (cvr: number | null): string =>
  cvr == null ? '미설정' : `${(cvr * 100).toFixed(1)}%`;

export const fmtConversions = (n: number | null): string =>
  n == null ? '미설정' : n.toLocaleString();

// ROAS는 매출(전환 가치) 추적 전엔 측정 불가 — null이면 "미측정".
export const fmtRoas = (roas: number | null): string =>
  roas == null ? '미측정' : `${roas.toFixed(2)}x`;

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

export type CampaignSource = 'live' | 'mock'; // live=실 Meta, mock=데모
export type CampaignsResponse = { campaigns: CampaignSummary[]; source?: CampaignSource };
export type CampaignView = 'table' | 'cards';
