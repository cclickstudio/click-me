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
  roas_estimated?: boolean; // true면 실측 아닌 고객 입력 전환가치 기반 추정 ROAS
  target_roas?: number | null; // 고객이 입력한 목표 ROAS (없으면 null)
  target_missed?: boolean; // 실제 ROAS가 목표 대비 미달(목표×0.7 미만)이면 true
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

// 추정 ROAS(estimated=true)는 실측과 구분해 '추정' 꼬리표를 붙인다 — 합성 아닌 가정 기반임을 명시.
export const fmtRoas = (
  roas: number | null,
  conversions: number | null,
  estimated?: boolean,
): string =>
  conversions == null ? '미설정' : `${(roas ?? 0).toFixed(2)}x${estimated ? ' (추정)' : ''}`;

export type CampaignSummary = CampaignKpi & {
  campaign_id: string;
  name: string;
  state: CampaignState;
  daily_budget_krw: number;
  ended_at?: string | null; // 게재 종료일(ISO) — 종료 사유 표시용
  delivery_blocked?: boolean; // 계정 자금 막힘 + ACTIVE인데 게재 중단
  block_reason?: string | null; // "선불 잔액 부족" 등
};

// 수동 입력 KPI — 전환 추적 전(0.0%/0.00x)인 캠페인에 고객이 직접 넣는 추정 CVR·ROAS.
// 실측이 아니라 '추정'이며 캠페인별로 localStorage에 저장(스펙: CVR·ROAS 재정의 #2).
export type ManualKpi = { cvr?: number; roas?: number }; // cvr=% , roas=배수
export type ManualKpiMap = Record<string, ManualKpi>;

// 계정 지갑 — 일일예산과 다른 '실제 충전·지출·잔액'(부가세 별도, KRW)
export type AccountWallet = {
  available_balance_krw?: number | null; // 사용 가능 잔액
  spend_cap_krw?: number | null; // 지출 한도(선불 충전액, 부가세 제외)
  amount_spent_krw?: number | null; // 누적 지출(광고 집행분)
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

export type DemographicMetrics = {
  age: string; // Meta 연령 버킷 (18-24, 25-34 …)
  gender: string; // female · male · unknown
  impressions: number;
  clicks: number;
  spend_krw: number;
  reach: number;
};
export type DemographicsResponse = { demographics: DemographicMetrics[] };

export type CreativePreview = {
  ad_id: string;
  ad_name: string;
  image_url: string | null; // 원본 해상도 (카드 메인 이미지)
  thumbnail_url: string | null; // 소형 썸네일 (image_url 없을 때 폴백)
  headline: string | null; // 광고 제목
  primary_text: string | null; // 기본 문구
};
export type CreativesResponse = { creatives: CreativePreview[] };

export type CampaignSource = 'live' | 'mock'; // live=실 Meta, mock=데모
export type CampaignsResponse = {
  campaigns: CampaignSummary[];
  source?: CampaignSource;
  account_block_reason?: string | null; // 계정 전체 게재 중단 사유 (배너용)
  auth_error?: string | null; // Meta 토큰 만료 등 인증 오류 — 재연결 안내 배너용
  account?: AccountWallet; // 계정 지갑(잔액·한도·지출)
};
export type CampaignView = 'table' | 'cards';
