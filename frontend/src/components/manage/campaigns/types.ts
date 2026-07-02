// 캠페인 목록·성과 대시보드 타입 — 백엔드 /campaigns 응답 대응

export type CampaignState =
  | 'draft'
  | 'under_review'
  | 'active'
  | 'active_pending_review'
  | 'paused'
  | 'ended'
  | 'archived'; // 보관/삭제 — '삭제됨 포함' 보기에서 노출

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
  frequency: number; // 조회기간 윈도 빈도(표시용)
  frequency_7d: number; // 최근 7일 빈도(노출 피로 판정용) — 조회기간 토글과 무관
  spend_today_krw: number; // 오늘 지출(소진율 분자) — 총 지출(spend_krw, 조회기간 누적)과 구분
  pacing_pct: number; // 오늘 지출÷일예산(%) — 조회기간 토글과 무관
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

export type MetricsStatus = 'ok' | 'permission'; // permission=권한 거부로 지표 못 불러옴
export type BudgetType = 'daily' | 'lifetime' | 'none'; // 일예산 / 총예산 / 미상

export type CampaignSummary = CampaignKpi & {
  campaign_id: string;
  name: string;
  state: CampaignState;
  daily_budget_krw: number;
  lifetime_budget_krw?: number; // 총예산(일예산 대신 쓰는 캠페인)
  budget_type?: BudgetType; // 일예산 표시·소진율 적용 분기
  metrics_status?: MetricsStatus; // 'permission'이면 지표를 '권한 없음'으로 표기
  ended_at?: string | null; // 게재 종료일(ISO) — 종료 사유 표시용
  delivery_blocked?: boolean; // 계정 자금 막힘 + ACTIVE인데 게재 중단
  block_reason?: string | null; // "선불 잔액 부족" 등
};

// 권한 거부 등으로 지표를 못 불러온 행인지 — true면 셀에 '권한 없음'/'—' 표시.
export const metricsBlocked = (c: { metrics_status?: MetricsStatus }): boolean =>
  c.metrics_status === 'permission';

// 예산 칸 표시 — 일예산 / 총예산 / 미상(—) 구분. 총예산 캠페인의 '일예산 ₩0' 오표기 방지.
export function budgetLabel(c: {
  daily_budget_krw: number;
  lifetime_budget_krw?: number;
  budget_type?: BudgetType;
}): string {
  if (c.budget_type === 'lifetime')
    return `총예산 ₩${(c.lifetime_budget_krw ?? 0).toLocaleString()}`;
  if (c.budget_type === 'none') return '—';
  return `₩${c.daily_budget_krw.toLocaleString()}`;
}

// 소진율 의미 분기 — 종료/권한없음/총예산(=하루 단위 아님)은 퍼센트 대신 라벨로.
export function pacingMeaningful(c: {
  state: CampaignState;
  budget_type?: BudgetType;
  metrics_status?: MetricsStatus;
}): boolean {
  return (
    c.state !== 'ended' &&
    c.state !== 'archived' &&
    !metricsBlocked(c) &&
    (!c.budget_type || c.budget_type === 'daily')
  );
}

// 수동 입력 KPI — 전환 추적 전(0.0%/0.00x)인 캠페인에 고객이 직접 넣는 추정 CVR·ROAS.
// 실측이 아니라 '추정'이며 캠페인별로 localStorage에 저장(스펙: CVR·ROAS 재정의 #2).
export type ManualKpi = { cvr?: number; roas?: number }; // cvr=% , roas=배수
export type ManualKpiMap = Record<string, ManualKpi>;

// 계정 지갑 — 일예산과 다른 '실제 충전·지출·잔액'(부가세 별도, KRW)
export type AccountWallet = {
  available_balance_krw?: number | null; // 선불 잔액
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

// 성과 미달 진단 — 백엔드 detection.performance_dx + (INCONCLUSIVE면) 진단 agent 산출.
// 없으면(정상이거나 목표 미입력) 백엔드가 null을 보내고 프론트는 노트를 숨긴다.
export type CampaignDiagnosis = {
  anomaly_type: string; // performance_below_target 등
  hypothesis: string; // 추정 원인 (한국어 한 문장)
  confidence: number; // 0~1
  source: string; // deterministic · agent
  status: string; // confirmed · inconclusive
};

export type CampaignDetail = {
  campaign_id: string;
  name: string;
  state: CampaignState;
  daily_budget_krw: number;
  lifetime_budget_krw?: number;
  budget_type?: BudgetType;
  metrics_status?: MetricsStatus;
  expected: number[];
  actual: number[];
  anomaly_hours: number[];
  series: DayPoint[];
  summary: CampaignKpi;
  diagnosis?: CampaignDiagnosis | null; // 성과 미달 진단(있을 때만)
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
  rate_limited?: string | null; // Meta 요청 한도(일시) — 기존 데이터 유지 + 안내 배너
  permission_error?: string | null; // 목록 자체 권한 거부 — '권한 없음' 안내 배너용
  not_connected?: string | null; // 로그인 org에 Meta 연결 없음 — '연결 필요' 안내 배너용
  account?: AccountWallet | null; // 계정 지갑(잔액·한도·지출)
  account_unavailable?: string | null; // 계정 자금 권한 없음 — 지갑 자리에 '권한 없음' 표시
  select_org?: string | null; // admin 무선택 — 조직 선택 안내(전체 집계 불가)
  total?: number; // 전체 캠페인 수(무한스크롤 진행률)
  has_more?: boolean; // 다음 페이지 존재 여부(무한스크롤 계속 로드 조건)
};
export type CampaignView = 'table' | 'cards';
