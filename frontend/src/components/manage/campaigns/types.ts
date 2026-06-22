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
  clicks: number;
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

// 규칙 하나 — conversions null(추적 미설정)=「미설정」, 그 외는 측정값 표기(구매 0이면 0.0%/0.00x).
// CVR·ROAS 동일 규칙으로 일관. 구매 0은 "측정 불가"가 아니라 "측정된 0"이라 숫자로 보인다.
export const fmtCvr = (cvr: number | null, conversions: number | null): string =>
  conversions == null ? '미설정' : `${((cvr ?? 0) * 100).toFixed(1)}%`;

export const fmtConversions = (n: number | null): string =>
  n == null ? '미설정' : `${n.toLocaleString()}건`;

export const fmtRoas = (roas: number | null, conversions: number | null): string =>
  conversions == null ? '미설정' : `${(roas ?? 0).toFixed(2)}x`;

export type CampaignSummary = CampaignKpi & {
  campaign_id: string;
  name: string;
  state: CampaignState;
  daily_budget_krw: number;
  delivery_blocked?: boolean; // 계정 자금 막힘 + ACTIVE인데 게재 중단
  block_reason?: string | null; // "선불 잔액 부족" 등
};

export type DayPoint = {
  label: string;
  impressions: number;
  clicks: number;
  reach: number;
  spend_krw: number;
  ctr: number;
  cpc_krw: number;
  cpm_krw: number;
  conversions: number | null;
  cvr: number | null;
  roas: number | null;
};

export type CampaignDetail = {
  campaign_id: string;
  name: string;
  state: CampaignState;
  daily_budget_krw: number;
  expected: number[];
  actual: number[];
  anomaly_hours: number[];
  series: DayPoint[];
  summary: CampaignKpi;
};

export type PlatformMetrics = {
  platform: string; // facebook · instagram · audience_network · messenger
  impressions: number;
  clicks: number;
  spend_krw: number;
  reach: number;
};
export type PlatformsResponse = { platforms: PlatformMetrics[] };

export type CampaignSource = 'live' | 'mock'; // live=실 Meta, mock=데모
export type CampaignsResponse = {
  campaigns: CampaignSummary[];
  source?: CampaignSource;
  account_block_reason?: string | null; // 계정 전체 게재 중단 사유 (배너용)
};
export type CampaignView = 'table' | 'cards';
