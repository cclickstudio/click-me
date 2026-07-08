import { getToken, refreshAccessToken } from "./authApi";
import type { BoardResponse } from "@/components/manage/compare/types";
import type { CampaignDetail, CampaignsResponse, CreativesResponse, DemographicsResponse, ManualKpiMap, PlatformsResponse } from "@/components/manage/campaigns/types";
import type { ActionResult, Proposal } from "@/components/manage/types";
import type { BudgetStatus } from "@/components/manage/budget/types";
import type {
  BrandKit,
  BrandKitInput,
  DebateResult,
  DebateSessionDetail,
  DebateSessionsResult,
  DebateStartResult,
  DebateTopic,
  DebateTopicsResult,
  QAEvent,
  ReportView,
  SimCompareInput,
  SimComparisonResult,
  SimRunInput,
  SimRunResult,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// 게재 불가 원인 — code별 한국어 message. INSUFFICIENT_CREDIT는 부족액·잔액 동반.
export interface DeliveryCause {
  code: string;
  message: string;
  need_krw?: number;
  balance_krw?: number; // Meta 선불 잔액(실광고비)
  credit_krw?: number; // ClickMe 크레딧 잔액(예산 한도)
  commit_krw?: number;
}
export interface ActivateResponse {
  serving: boolean;
  result: { status?: string; failure_reason?: string | null } | null;
  balance_krw: number; // Meta 선불 잔액(실광고비)
  credit_krw?: number; // ClickMe 크레딧 잔액(예산 한도)
  commit_krw: number;
  causes: DeliveryCause[];
  error_message?: string;
}
export interface DeliveryStatusResponse {
  campaign_id: string;
  serving: boolean;
  effective_status: string;
  issues: string[];
  causes: DeliveryCause[];
  spend_cap_krw?: number | null;
  balance_krw: number;
}
export interface PauseResponse {
  paused: boolean;
  result: { status?: string; failure_reason?: string | null } | null;
  error_message?: string;
}
// 실 캠페인 성과 이상 스캔
export interface AnomalyScanItem {
  campaign_id: string;
  name: string;
  state: string;
  diagnosis: { anomaly_type: string; hypothesis?: string } & Record<string, unknown>;
  suggested_action?: string; // REPLACE_CREATIVE 등 — CTA 렌더용
}
// 예산 리밸런싱 제안 — 하이브리드. 2개+는 이전(transfer), 1개는 단일 증액/감액(adjust).
export interface RebalanceSide {
  campaign_id: string;
  name: string;
  cpc_krw: number;
  daily_budget_krw: number;
  after_krw: number;
}
// 캠페인 2개+ — 저효율→고효율 일예산 이동(적용은 budget-commit 2건). kind 없으면 하위호환으로 이전.
export interface RebalanceTransfer {
  kind?: 'transfer';
  from: RebalanceSide;
  to: RebalanceSide;
  move_krw: number;
  basis: string;
  reason: string;
}
// 캠페인 1개 — 그 캠페인 일예산을 소진율 기준 증액/감액(적용은 budget-commit 1건).
export interface RebalanceAdjust {
  kind: 'adjust';
  direction: 'increase' | 'decrease';
  campaign: RebalanceSide;
  move_krw: number;
  basis: string;
  reason: string;
}
export type RebalanceProposal = RebalanceTransfer | RebalanceAdjust;
// 성과 리포트 — 선택 기간 실측 요약(결정론). since는 maximum이면 null(전체 기간).
export interface WeeklyReport {
  period: { since: string | null; until: string; label?: string };
  totals: {
    spend_krw: number;
    impressions: number;
    clicks: number;
    conversions: number;
    ctr: number;
    cpc_krw: number;
  };
  campaigns: {
    campaign_id: string;
    name: string;
    state: string;
    spend_krw: number;
    impressions: number;
    clicks: number;
    conversions: number | null;
    ctr: number;
    cpc_krw: number;
    frequency: number;
  }[];
  highlights: string[];
  next_actions: string[];
}
export interface AnomalyScanResponse {
  source: string;
  scanned: number;
  anomalies: AnomalyScanItem[];
  note?: string;
}
export interface SyncResponse {
  campaign_id: string;
  spend_krw: number;
  charged_now_krw: number;
  balance_krw: number;
  effective_status: string;
  ended: boolean;
}
export interface LeadRecord {
  created_time: string;
  fields: Record<string, string>;
}
export interface LeadsResponse {
  leads: LeadRecord[];
  count: number;
  note?: string;
}
// 집행 전(시뮬 예측) — 실 시뮬 KPI와 동일 필드(슬롯). source=mock|sim
export interface PredictionSnapshot {
  ad_id: string;
  click_intent_rate: number;
  purchase_intent: number;
  trust_avg: number;
  rejection_rate: number;
  as_of: string;
  source: string;
}
// 집행 후(실측)
export interface ActualOutcome {
  campaign_id: string;
  impressions: number;
  reach: number;
  spend_krw: number;
  ctr: number;
  cpc_krw: number;
  cpm_krw: number;
  conversions?: number | null;
  cvr?: number | null;
  roas?: number | null;
}
export interface BeforeAfterItem {
  campaign_id: string;
  name: string;
  simulation_id?: string | null; // 링크된 시뮬 id — 결과 페이지(/simulation/{id}) 이동용(없으면 미연결)
  prediction: PredictionSnapshot | null;
  actual: ActualOutcome;
  verdict: 'aligned' | 'overperformed' | 'underperformed' | 'unknown';
  rationale: string;
  interpretation?: string; // 보조 KPI 기반 결정론 해석 — 없으면 빈 문자열
  pred_strong?: boolean | null; // 클릭 의향률 강함(≥20%) 통과 — 예측 없으면 null
  act_strong?: boolean | null; // 실측 CTR 양호(≥1%) 통과 — 판정 불가면 null
  purchase_pred_strong?: boolean | null; // 구매의도 강함(≥3.5/5) 통과 — 예측 없으면 null
  purchase_act_strong?: boolean | null; // 실측 CVR 양호(≥2%) 통과 — CVR null(추적 전)·예측 미연결이면 null
}
export interface BeforeAfterResponse {
  items: BeforeAfterItem[];
  rate_limited?: string; // Meta 요청 한도 시 안내
}

// 베이스라인 앵커 — 집행된 광고의 예측↔실측 쌍(절대 비교 금지, 순위 정합에만 사용)
export interface CalibrationAnchor {
  campaign_id: string;
  name: string;
  source: string;
  predicted_click_intent: number; // 0~1
  actual_ctr: number; // 0~1
  predicted_purchase_intent: number; // 1~5
  actual_cvr: number | null; // 0~1 (추적 전이면 null)
  predicted_rejection: number; // 0~1
  actual_impressions: number;
  actual_spend_krw: number;
}
export interface CalibrationSummary {
  n: number;
  concordance_click: number | null; // 예측 클릭의향률 vs 실측 CTR 순위 일치율(0~1)
  concordance_purchase: number | null; // 예측 구매의도 vs 실측 CVR 순위 일치율(0~1)
  unlock_threshold: number;
  unlocked: boolean;
}
export interface CalibrationResponse {
  anchors: CalibrationAnchor[];
  summary: CalibrationSummary;
  rate_limited?: string;
}

// admin이 impersonate로 선택한 org id — management 요청에만 X-Org-Id로 실림. sessionStorage=탭 종료 시 소멸.
export function getAdminOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem("adminOrgId");
}
export function setAdminOrgId(orgId: string | null): void {
  if (typeof window === "undefined") return;
  if (orgId) window.sessionStorage.setItem("adminOrgId", orgId);
  else window.sessionStorage.removeItem("adminOrgId");
}

// 공용 fetch — access 토큰(쿠키)을 Authorization 헤더에 싣고 쿠키도 함께 보낸다(credentials).
// 401이면 refresh 토큰으로 access 재발급 후 1회 재시도. 모든 API 호출(request·직접 fetch)이 이걸 쓴다.
// credentials: "include" 는 EventSource가 못 쓰는 SSE 외 경로에도 쿠키를 실어 백엔드 쿠키 폴백과 정합.
// 화면의 직접 fetch도 이 함수로 통일 — 개별 `Bearer ${getToken()}`·`authHeaders()` 대신 이걸 쓴다.
export async function authedFetch(url: string, init: RequestInit = {}): Promise<Response> {
  // admin이 선택한 대상 org(impersonation). management·projects·generator가 X-Org-Id로 소비한다.
  // adminOrgId는 admin만 설정되므로(로그아웃 시 소거) 모든 요청에 실어도 비-admin엔 무영향.
  const orgId = getAdminOrgId();
  const build = (token: string | null): RequestInit => ({
    ...init,
    credentials: "include",
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(orgId ? { "X-Org-Id": orgId } : {}),
    },
  });
  let res = await fetch(url, build(getToken()));
  if (res.status === 401) {
    const nt = await refreshAccessToken();
    if (nt) res = await fetch(url, build(nt));
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // X-Org-Id(admin 선택 org)·인증·refresh는 authedFetch가 일괄 처리한다.
  const { headers: initHeaders, ...restInit } = init ?? {};
  const res = await authedFetch(`${API_BASE}/api${path}`, {
    ...restInit,
    headers: {
      "Content-Type": "application/json",
      ...(initHeaders as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    // detail이 dict(예: {issues:[...]})면 그대로 두면 "[object Object]"가 되니 읽히게 직렬화.
    const d = (err as { detail?: unknown }).detail;
    const msg =
      typeof d === "string" ? d : d != null ? JSON.stringify(d) : `HTTP ${res.status}`;
    throw new ApiError(msg, res.status);
  }
  return res.json();
}

// 시뮬 multipart 폼 빌드 — run(동기)·start(비동기 SSE)가 공용으로 사용.
function buildSimForm(input: SimRunInput): FormData {
  const form = new FormData();
  form.append("ad_id", input.ad_id);
  if (input.ad_content) form.append("ad_content", input.ad_content);
  if (input.ad_image) form.append("ad_image", input.ad_image);
  if (input.ad_image_url) form.append("ad_image_url", input.ad_image_url);
  if (input.organization_id) form.append("organization_id", input.organization_id);
  if (input.project_id) form.append("project_id", input.project_id);
  if (input.target_filter && Object.keys(input.target_filter).length > 0)
    form.append("target_filter", JSON.stringify(input.target_filter));
  if (input.target_mode) form.append("target_mode", input.target_mode);
  if (input.sample_size != null) form.append("sample_size", String(input.sample_size));
  if (input.allocation) form.append("allocation", input.allocation);
  if (input.ad_title) form.append("ad_title", input.ad_title);
  if (input.product_category) form.append("product_category", input.product_category);
  if (input.ad_objective) form.append("ad_objective", input.ad_objective);
  if (input.service_class != null) form.append("service_class", String(input.service_class));
  if (input.analysis_mode) form.append("analysis_mode", input.analysis_mode);
  if (input.from_campaign_id) form.append("from_campaign_id", input.from_campaign_id);
  if (input.generation_id) form.append("generation_id", input.generation_id);
  return form;
}

// Persona Set 비교 multipart 폼 — 광고 공통 필드 + segments JSON.
function buildCompareForm(input: SimCompareInput): FormData {
  const form = new FormData();
  form.append("ad_id", input.ad_id);
  if (input.ad_content) form.append("ad_content", input.ad_content);
  if (input.ad_image) form.append("ad_image", input.ad_image);
  if (input.ad_image_url) form.append("ad_image_url", input.ad_image_url);
  if (input.organization_id) form.append("organization_id", input.organization_id);
  if (input.project_id) form.append("project_id", input.project_id);
  if (input.ad_title) form.append("ad_title", input.ad_title);
  if (input.product_category) form.append("product_category", input.product_category);
  if (input.ad_objective) form.append("ad_objective", input.ad_objective);
  if (input.service_class != null) form.append("service_class", String(input.service_class));
  form.append("segments", JSON.stringify(input.segments));
  return form;
}

// 캠페인 조회 쿼리스트링 — 전환가치·목표 ROAS는 입력됐을 때만 붙인다.
// 조회 기간 토글 — 전체 누적(maximum) / 최근 30일 / 이번 달. Ads Manager와 맞추기용.
export type DatePreset = "maximum" | "last_30d" | "this_month";
// 성과 리포트 기간 — 캠페인 토글 + 주간(last_7d)까지. 리포트 전용이라 별도 타입.
export type ReportPeriod = DatePreset | "last_7d";

function _campaignQuery(
  conversionValueKrw?: number | null,
  targetRoas?: number | null,
  datePreset?: DatePreset,
  includeArchived?: boolean,
  page?: { limit?: number; offset?: number },
  includeSeries?: boolean,
): string {
  const p = new URLSearchParams();
  if (conversionValueKrw) p.set("conversion_value_krw", String(conversionValueKrw));
  if (targetRoas) p.set("target_roas", String(targetRoas));
  if (datePreset && datePreset !== "maximum") p.set("date_preset", datePreset);
  if (includeArchived) p.set("include_archived", "true");
  if (page?.limit != null) p.set("limit", String(page.limit));
  if (page?.offset != null) p.set("offset", String(page.offset));
  if (includeSeries) p.set("include_series", "true");
  const q = p.toString();
  return q ? `?${q}` : "";
}

// 채팅 세션·메시지(DB 영속) — 프로젝트별 채팅 목록과 내역.
export type ChatSessionRow = {
  id: string;
  title: string;
  project_id: string | null;
  message_count: number;
  unread_count?: number; // N5 미확인(마지막 열람 이후 assistant 메시지 수)
  created_at: string | null;
  updated_at: string | null;
};
// 센터 통합 세션(org 전체) — ChatSessionRow + project_name.
export type CenterSessionRow = ChatSessionRow & { project_name?: string | null };
// 센터 알림 병합 항목 — source로 management 이상감지/center 제안을 구분.
export type CenterNotificationItem = {
  source: 'management' | 'center_suggestion';
  id: string;
  project_id: string | null;
  project_name?: string | null;
  read_at?: string | null;
  created_at?: string | null;
  payload?: Record<string, unknown>;
  // center 제안 전용
  suggestion_type?: 'sim_suggest' | 'gen_suggest' | 'launch_suggest';
  reason?: string | null;
  source_sim_id?: string | null;
  source_gen_id?: string | null;
  // management 이상감지 전용
  kind?: string | null;
  campaign_id?: string | null;
  resolution?: string | null;
  followup_count?: number | null;
};
export type ChatHistoryMessage = {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  meta?: unknown;
  created_at?: string | null;
};

export interface AutomationRunItem {
  id: string;
  domain: string;
  job_name: string;
  status: string;
  severity: string | null;
  title: string;
  body: string;
  suggested_action: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
  resolved_at: string | null;
}
// 운영 알림(이상 감지 C안) — 스펙 2026-07-03 §2
export type ManagementNotification = {
  id: string;
  project_id: string;
  project_name: string;
  campaign_id: string | null;
  kind: string;
  payload: {
    campaign_name?: string;
    message?: string;
    anomaly_type?: string;
    options?: { index: number; action: string; tool_hint: string | null; label: string }[];
    kind?: string; // "account"면 계정 단위 정보성 알림(캠페인·상담 없음)
    title?: string; // 계정 알림 제목(예: "지갑 거의 소진")
    rule?: string;
  };
  read_at: string | null;
  resolved_at: string | null;
  resolution: string | null;
  followup_count: number;
  last_notified_at: string;
  created_at: string | null;
};

export const api = {
  ads: {
    upload: (file: File, projectId: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("project_id", projectId);
      return authedFetch(`${API_BASE}/api/ads/upload`, { method: "POST", body: form }).then((r) => r.json());
    },
    analyzeImage: (body: { ad_id: string; image_url: string }) =>
      request("/ads/analyze/image", { method: "POST", body: JSON.stringify(body) }),
    analyzeText: (body: { ad_id: string; text_content: { headline: string; body: string; cta: string } }) =>
      request("/ads/analyze/text", { method: "POST", body: JSON.stringify(body) }),
  },

  personas: {
    generate: (body: object) => request("/personas/generate", { method: "POST", body: JSON.stringify(body) }),
  },

  // 도메인 시뮬레이션(DDD) — multipart/form-data. run=동기(레거시), start=비동기 SSE.
  simulation: {
    // 동기 실행 — 끝까지 돌린 결과를 한 번에 반환(진행률 없음).
    run: (input: SimRunInput): Promise<SimRunResult> => {
      // Content-Type은 지정하지 않는다 — 브라우저가 multipart boundary를 자동 설정.
      return authedFetch(`${API_BASE}/api/simulation/run`, {
        method: "POST",
        body: buildSimForm(input),
      }).then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
          throw new Error(err.detail ?? `HTTP ${r.status}`);
        }
        return r.json();
      });
    },
    // 비동기 시작 — run_id 반환. 진행률은 stream(SSE), 결과는 result(GET).
    start: (
      input: SimRunInput,
    ): Promise<{ run_id: string; stream_url: string; result_url: string; mode: string }> => {
      return authedFetch(`${API_BASE}/api/simulation`, {
        method: "POST",
        body: buildSimForm(input),
      }).then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
          throw new Error(err.detail ?? `HTTP ${r.status}`);
        }
        return r.json();
      });
    },
    // Persona Set 비교 시작 — 세그먼트 배열로 compare, run_id 반환.
    // 진행률은 stream(run_id) 재사용(이벤트에 segment_* 추가), 결과는 compareResult(run_id).
    compare: (input: SimCompareInput): Promise<{ run_id: string }> => {
      return authedFetch(`${API_BASE}/api/simulation/compare`, {
        method: "POST",
        body: buildCompareForm(input),
      }).then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
          throw new Error(err.detail ?? `HTTP ${r.status}`);
        }
        return r.json();
      });
    },
    // compare 결과 — mode:"persona_set" + 세그먼트별 SimRunResult.
    compareResult: (runId: string): Promise<SimComparisonResult> =>
      request<SimComparisonResult>(`/simulation/${runId}/result`),
    // withCredentials: SSE는 Authorization 헤더를 못 붙이므로 쿠키로 인증(백엔드 쿠키 폴백).
    stream: (runId: string) =>
      new EventSource(`${API_BASE}/api/simulation/${runId}/stream`, { withCredentials: true }),
    // 진행 상태(running/completed/failed/unknown) — 새로고침 후 백그라운드 런 복원용.
    status: (
      runId: string,
    ): Promise<{ run_id: string; status: string; pct: number; stage: string | null }> =>
      request(`/simulation/${runId}/status`),
    result: (runId: string): Promise<SimRunResult> =>
      request<SimRunResult>(`/simulation/${runId}/result`),
    // DB에 저장된 시뮬 결과를 simulation_id로 조회(콜드·패널 진입). 404=결과 없음.
    dbResult: (simulationId: string): Promise<SimRunResult> =>
      request<SimRunResult>(`/simulation/${simulationId}/db-result`),
    // VLM이 이 URL 이미지를 읽을 수 있는지 사전 확인(백엔드가 직접 GET — 미리보기와 별개).
    checkImage: (url: string): Promise<{ ok: boolean; mime?: string; reason?: string }> =>
      request(`/simulation/check-image?url=${encodeURIComponent(url)}`),
    // Individual 모드 — 고정 패널에서 특정 페르소나 지정 선택용 미리보기 목록.
    panelPersonas: (params: {
      gender?: string;
      age_min?: number;
      age_max?: number;
      limit?: number;
      offset?: number;
    }): Promise<{
      items: {
        persona_id: string;
        age: number;
        gender: string;
        region: string;
        narrative_snippet: string;
      }[];
      total: number;
    }> => {
      const qs = new URLSearchParams();
      if (params.gender) qs.set('gender', params.gender);
      if (params.age_min != null) qs.set('age_min', String(params.age_min));
      if (params.age_max != null) qs.set('age_max', String(params.age_max));
      qs.set('limit', String(params.limit ?? 30));
      qs.set('offset', String(params.offset ?? 0));
      return request(`/simulation/panel/personas?${qs.toString()}`);
    },
  },

  // 페르소나 토론(/api/debate/*) — 시뮬 반응(reactions)을 받아 토론을 돌리고 결과를 낸다.
  debate: {
    // 추가 토론용 논제 후보 5개 → ranking 순. 안 호출하면 최초 토론(분석 headline 고정).
    topics: (body: {
      reactions: unknown[];
      ad_analysis?: unknown;
      personas?: unknown[];
      ad_title?: string; // 광고 제목 — 후보 topic에 동봉(토론자 grounding)
      ad_description?: string; // 광고 설명 — 동상
    }): Promise<DebateTopicsResult> =>
      request<DebateTopicsResult>("/debate/topics", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // 시뮬 반응으로 토론 시작 → run_id. 토론은 항상 실 LLM, lay_count는 일반인 수(2|3|4).
    // topic을 주면 그 논제로 추가 토론, 안 주면 최초 토론(분석 headline 고정).
    start: (
      body: {
        reactions: unknown[];
        ad_analysis?: unknown;
        personas?: unknown[];
        simulation_id?: string;
        topic?: DebateTopic;
        rubric_scores?: unknown[]; // §4 루브릭(있으면 리포트 진단에 실음)
        objective_fit?: unknown; // 캠페인 목표 적합도(ReportView 메인 판정)
        ad_title?: string; // 광고 제목 — 최초 토론 topic에 동봉(토론자 grounding)
        ad_description?: string; // 광고 설명 — 동상
      },
      opts?: { layCount?: 2 | 3 | 4 },
    ): Promise<DebateStartResult> => {
      const q = new URLSearchParams();
      if (opts?.layCount) q.set("lay_count", String(opts.layCount));
      return request<DebateStartResult>(`/debate/start?${q.toString()}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    stream: (runId: string) =>
      new EventSource(`${API_BASE}/api/debate/${runId}/stream`, { withCredentials: true }),
    result: (runId: string): Promise<DebateResult> => request<DebateResult>(`/debate/${runId}/result`),
    // 시뮬의 저장된 토론 목록(메타) — 세션 탭·프로젝트 패널 복원용. DB 미연동이면 빈 목록.
    bySimulation: (simulationId: string): Promise<DebateSessionsResult> =>
      request<DebateSessionsResult>(`/debate/by-simulation/${simulationId}`),
    // 저장된 토론 1건 상세(참가자·발언·judge_log·final) — 채팅·결과 복원용.
    detail: (debateId: string): Promise<DebateSessionDetail> =>
      request<DebateSessionDetail>(`/debate/${debateId}/detail`),
    // 시뮬에 저장된 통합 리포트(ReportView) 복원 — 콜드·새로고침·패널 진입용.
    // request 헬퍼는 404에 throw하므로 여기선 fetch 직접 호출 → 404·실패 시 null 반환(결과 화면은 떠야 함).
    savedReport: async (simulationId: string): Promise<ReportView | null> => {
      const res = await authedFetch(
        `${API_BASE}/api/debate/by-simulation/${simulationId}/report`,
      );
      if (!res.ok) return null;
      return res.json() as Promise<ReportView>;
    },
    // 토론 종료 후 Q&A — POST라 EventSource 불가 → fetch + ReadableStream으로 "data: {json}\n\n" 파싱.
    question: async (
      runId: string,
      body: { question: string; reactions: unknown[]; ad_analysis?: unknown },
      onEvent: (ev: QAEvent) => void,
    ): Promise<void> => {
      const res = await authedFetch(`${API_BASE}/api/debate/${runId}/question`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // "data: {json}\n\n" 단위로 끊어 파싱.
      const flush = (chunk: string) => {
        buffer += chunk;
        let sep: number;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          for (const line of raw.split("\n")) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const payload = trimmed.slice(5).trim();
            if (!payload) continue;
            try {
              onEvent(JSON.parse(payload) as QAEvent);
            } catch {
              // 부분 JSON·keep-alive는 무시.
            }
          }
        }
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        flush(decoder.decode(value, { stream: true }));
      }
      flush(decoder.decode());
    },
  },

  chat: {
    complete: () => `${API_BASE}/api/chat/complete`,
    // 프로젝트별 세션 목록(최근 갱신 순).
    sessions: (projectId: string) =>
      request<{ sessions: ChatSessionRow[] }>(
        `/chat/sessions?project_id=${encodeURIComponent(projectId)}`,
      ),
    createSession: (projectId: string, title?: string) =>
      request<ChatSessionRow>("/chat/sessions", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, title }),
      }),
    messages: (sessionId: string) =>
      request<{ session_id: string; messages: ChatHistoryMessage[] }>(
        `/chat/sessions/${sessionId}/messages`,
      ),
    // 개선 루프(시뮬↔제너) 상태 — 제안 숨김/조기종료 배지에 쓴다.
    // simulationId를 주면 그 시뮬 KPI 등급으로 조기종료를 판정한다(3턴 전이라도 강하면 종료).
    loopState: (sessionId: string, simulationId?: string) =>
      request<{
        loop_count: number;
        max_loop: number;
        can_improve: boolean;
        phase: string;
        early_stop_reason?: string | null;
      }>(
        `/chat/loop-state?session_id=${encodeURIComponent(sessionId)}` +
          (simulationId ? `&simulation_id=${encodeURIComponent(simulationId)}` : '')
      ),
    // 미확인 알림(N5) — 라우트 변경마다 폴링해 벨 배지·패널에 표시.
    notifications: (projectId: string) =>
      request<{
        notifications: {
          session_id: string;
          title: string;
          preview: string;
          unread_count: number;
        }[];
      }>(`/chat/notifications?project_id=${encodeURIComponent(projectId)}`),
    // 세션 열람 처리(N5) — 해당 세션을 미확인에서 제거.
    markRead: (sessionId: string) =>
      request<{ ok: boolean }>(`/chat/sessions/${sessionId}/read`, { method: "POST" }),
    deleteSession: (sessionId: string) =>
      request<{ deleted: boolean }>(`/chat/sessions/${sessionId}`, { method: "DELETE" }),
    // 메시지 핀 토글(T19) — 세션 상단 고정.
    pinMessage: (messageId: string, pinned: boolean) =>
      request<{ id: string; pinned: boolean }>(`/chat/messages/${messageId}/pin`, {
        method: "PATCH",
        body: JSON.stringify({ pinned }),
      }),
    // 결과 요약 — 채팅 목록/카드 위젯용(kind=sim: 4대 KPI, gen: 후보 요약).
    resultSummary: (kind: 'sim' | 'gen', id: string) =>
      request<Record<string, unknown>>(
        `/chat/result-summary?kind=${kind}&id=${encodeURIComponent(id)}`,
      ),
    // 단독 위젯 메시지 영속화(시뮬 결과·토론 stream·토론 요약) — 새로고침 복원용. 저장된 메시지 반환.
    appendWidgets: (sessionId: string, items: { content?: string; meta?: object }[]) =>
      request<{ messages: ChatHistoryMessage[] }>("/chat/widget-messages", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, items }),
      }),
    // N1 — 프로젝트의 활성(최신) 채팅 세션 id 해석. 없으면 새로 만든다. 실패 시 null.
    resolveActiveSession: async (projectId: string): Promise<string | null> => {
      try {
        const { sessions } = await api.chat.sessions(projectId);
        if (sessions && sessions.length > 0) return sessions[0].id;
        const created = await api.chat.createSession(projectId, "시뮬레이션 알림");
        return created.id;
      } catch {
        return null;
      }
    },
    // 첨부 이미지 S3 업로드 → 프록시 URL(상대경로) 반환. 내역 영속화에 사용.
    uploadImage: async (file: File): Promise<{ key: string; url: string }> => {
      const form = new FormData();
      form.append("file", file);
      const res = await authedFetch(`${API_BASE}/api/chat/image`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      return res.json();
    },
    // F10 — 광고 맥락 기반 추천 해시태그·키워드(SNS 활용). 칩으로 복사.
    keywords: (body: {
      product?: string;
      category?: string;
      target?: string;
      copy_text?: string;
      context?: string;
    }) =>
      request<{ hashtags: string[]; keywords: string[] }>("/chat/keywords", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // P5 — 인용 칩 원문 펼침. 출처 파일(+섹션)로 KB 청크 텍스트를 조회.
    kbChunk: (source: string, title?: string) =>
      request<{ source: string; title: string; chunk: string }>(
        `/chat/kb-chunk?source=${encodeURIComponent(source)}${
          title ? `&title=${encodeURIComponent(title)}` : ""
        }`,
      ),
    // 어시스턴트 답변 피드백(좋아요/싫어요) — RAG 품질 개선 적재.
    feedback: (body: {
      thread_id?: string;
      rating?: number;
      question?: string;
      answer?: string;
      failure_type?: string;
    }) => request("/chat/feedback", { method: "POST", body: JSON.stringify(body) }),
  },

  // 센터(우측 통합 알림) — management 이상감지 + center 제안 병합 조회, org 통합 세션.
  center: {
    // 알림 센터 병합 목록 — project_id 생략 시 org 전체. COMPANY는 제안 숨김(백엔드 처리).
    notifications: (projectId?: string) =>
      request<{
        items: CenterNotificationItem[];
        unread_count: number;
        org_selected: boolean;
      }>(
        `/center/notifications${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
      ),
    // 채팅 센터 통합 세션 — project_id 생략 시 org 전체 프로젝트.
    sessions: (projectId?: string) =>
      request<{ sessions: CenterSessionRow[]; org_selected: boolean }>(
        `/center/sessions${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
      ),
    // 제안 알림 읽음(아코디언 열 때) / 무시.
    readSuggestion: (id: string) =>
      request<{ ok: boolean }>(`/center/suggestions/${id}/read`, { method: "POST" }),
    dismissSuggestion: (id: string) =>
      request<{ ok: boolean }>(`/center/suggestions/${id}/dismiss`, { method: "POST" }),
  },

  inquiries: {
    create: (body: { title: string; content: string; contact_email?: string }) =>
      request("/inquiries", { method: "POST", body: JSON.stringify(body) }),
  },

  admin: {
    users: () => request<{ users: unknown[] }>("/admin/users"),
    createUser: (body: object) => request("/admin/users", { method: "POST", body: JSON.stringify(body) }),
    inquiries: () =>
      request<{
        inquiries: {
          id: string;
          title: string;
          content: string;
          contact_email: string | null;
          is_resolved: boolean;
          created_at: string;
          resolved_at: string | null;
        }[];
      }>("/admin/inquiries"),
    resolveInquiry: (id: string, resolved: boolean) =>
      request(`/admin/inquiries/${id}/resolve?resolved=${resolved}`, { method: "PATCH" }),
    // 조직 목록(배열 직접 반환) — admin impersonation org 선택 드롭다운용.
    organizations: () => request<{ id: string; name: string }[]>("/admin/organizations"),
  },

  projects: {
    // GET /projects 는 배열을 직접 반환한다(래핑 객체 아님).
    list: () => request<unknown[]>("/projects"),
    create: (body: { name: string; description?: string }) =>
      request("/projects", { method: "POST", body: JSON.stringify(body) }),
    get: (id: string) => request(`/projects/${id}`),
    // 프로젝트별 시뮬/생성 목록(배열 직접 반환) — 채팅 슬래시 /시뮬목록·/시안목록용.
    simulations: (id: string, limit = 20) =>
      request<Record<string, unknown>[]>(`/projects/${id}/simulations?limit=${limit}`),
    generations: (id: string, limit = 20) =>
      request<Record<string, unknown>[]>(`/projects/${id}/generations?limit=${limit}`),
  },

  billing: {
    createOrder: (amountKrw: number) =>
      request<{ order_id: string; amount_krw: number; client_key: string }>("/billing/orders", {
        method: "POST",
        body: JSON.stringify({ amount_krw: amountKrw }),
      }),
    confirm: (body: { payment_key: string; order_id: string; amount_krw: number }) =>
      request<{ order_id: string; status: string; amount_krw: number; balance_krw: number }>(
        "/billing/confirm",
        { method: "POST", body: JSON.stringify(body) },
      ),
    cancel: (orderId: string, reason = "사용자 요청") =>
      request<{ order_id: string; status: string; amount_krw: number; balance_krw: number }>(
        "/billing/cancel",
        { method: "POST", body: JSON.stringify({ order_id: orderId, reason }) },
      ),
    balance: () => request<{ org_id: string; balance_krw: number }>("/billing/balance"),
    history: () =>
      request<{
        org_id: string;
        entries: {
          entry_id: string;
          delta_krw: number;
          balance_after_krw: number;
          reason: string;
          ref_id: string;
          created_at: string;
        }[];
      }>("/billing/history"),
  },

  management: {
    run: (fault: string) => request(`/management/run?fault=${fault}`),
    regenerate: (diagnosis: unknown) =>
      request("/management/regenerate", { method: "POST", body: JSON.stringify({ diagnosis }) }),
    // 집행 권장 게이트 임계값 — 판정 정본은 서버, 프론트는 버튼 활성/안내 동기화용
    execGate: () =>
      request<{ min_click_intent_rate: number; max_rejection_rate: number }>(
        "/management/exec-gate",
      ),
    approve: (proposal: unknown, approved: boolean) =>
      request("/management/approve", {
        method: "POST",
        body: JSON.stringify({ proposal, approved }),  // approver_id는 서버가 주입
      }),
    execute: (approved_action: unknown, proposal: unknown) =>
      request("/management/execute", {
        method: "POST",
        body: JSON.stringify({ approved_action, proposal }),
      }),
    budgetProposal: (
      campaignId: string,
      body: {
        action: 'increase_budget' | 'decrease_budget';
        new_daily_budget_krw: number;
        shown_budget_before_krw?: number;
      },
    ) =>
      request<{ proposal: Proposal; budget_before_krw: number; drift: boolean }>(
        `/management/campaigns/${campaignId}/budget-proposal`,
        { method: "POST", body: JSON.stringify(body) },
      ),
    budgetCommit: (
      campaignId: string,
      body: {
        action: 'increase_budget' | 'decrease_budget';
        new_daily_budget_krw: number;
        shown_budget_before_krw?: number;
      },
    ) =>
      request<{
        result: ActionResult;
        error_message?: string;
        budget_before_krw: number;
        budget_after_krw: number;
      }>(`/management/campaigns/${campaignId}/budget-commit`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    replaceCreativeProposal: (
      campaignId: string,
      body: { generation_id: string; candidate_id: string; link_url?: string },
    ) =>
      request<{
        proposal: Proposal;
        preview: {
          candidate: { headline?: string | null; body?: string | null; s3_key?: string | null };
          affected_ads: {
            ad_id: string;
            ad_name: string;
            thumbnail_url?: string | null;
            image_url?: string | null;
            headline?: string | null;
            primary_text?: string | null;
            link_url?: string | null;
          }[];
        };
      }>(`/management/campaigns/${campaignId}/replace-creative-proposal`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    audit: (approvalId: string) => request(`/management/audit?approval_id=${approvalId}`),
    // 멀티테넌트 — 로그인 org로 Meta OAuth 로그인 URL을 받는다(인증 XHR). 프론트가 그 URL로 이동.
    connectMeta: () => request<{ login_url: string; state: string }>("/management/meta/connect"),
    compareBoard: () => request<BoardResponse>("/management/compare/board"),
    // 집행 전(시뮬 예측) vs 후(실측) — ClickMe로 만든 캠페인별
    beforeAfter: () => request<BeforeAfterResponse>("/management/compare/before-after"),
    calibrationAnchors: () =>
      request<CalibrationResponse>("/management/calibration/anchors"),
    // 캠페인 생성 정책 — 최소예산(Meta 실시간)·특별광고카테고리·연령. 폼이 동적 검증에 사용.
    campaignPolicy: () =>
      request<{
        min_daily_budget_krw: number;
        min_by_objective_krw: Record<string, number>;
        special_ad_categories: { value: string; label: string }[];
        age_min: number;
        age_max: number;
      }>("/management/campaign-policy"),
    // conversionValueKrw(전환 가치)→추정 ROAS, targetRoas(목표)→목표 미달 판정.
    campaigns: (
      conversionValueKrw?: number | null,
      targetRoas?: number | null,
      datePreset?: DatePreset,
      includeArchived?: boolean,
      page?: { limit?: number; offset?: number },
      includeSeries?: boolean, // 홈·모니터링 스파크라인용 일별 지출을 목록에 포함(상세 N콜 제거)
    ) =>
      request<CampaignsResponse>(
        `/management/campaigns${_campaignQuery(conversionValueKrw, targetRoas, datePreset, includeArchived, page, includeSeries)}`,
      ),
    campaign: (
      id: string,
      conversionValueKrw?: number | null,
      targetRoas?: number | null,
      datePreset?: DatePreset,
    ) =>
      request<CampaignDetail>(
        `/management/campaigns/${id}${_campaignQuery(conversionValueKrw, targetRoas, datePreset)}`,
      ),
    // 예산 리밸런싱 제안 — 최근 7일 CPC 격차 기반(제안만, 적용은 budgetCommit 2건)
    rebalanceProposal: () =>
      request<{ proposal: RebalanceProposal | null; note: string | null }>(
        `/management/budget/rebalance-proposal`,
      ),
    // 성과 리포트 — 선택 기간 실측 요약(총합·캠페인별·하이라이트·다음 액션). 기본 last_7d.
    weeklyReport: (period?: ReportPeriod) =>
      request<{ report: WeeklyReport | null; note: string | null }>(
        `/management/report/weekly${period ? `?period=${period}` : ""}`,
      ),
    // 실 캠페인 성과 이상 스캔 — live에서 캠페인별 성과 진단(ROAS 미달 등)을 모아 반환.
    anomalyScan: (targetRoas?: number | null) =>
      request<AnomalyScanResponse>(
        `/management/anomaly/scan${targetRoas ? `?target_roas=${targetRoas}` : ""}`,
      ),
    campaignPlatforms: (id: string) =>
      request<PlatformsResponse>(`/management/campaigns/${id}/platforms`),
    campaignDemographics: (id: string) =>
      request<DemographicsResponse>(`/management/campaigns/${id}/demographics`),
    campaignCreatives: (id: string) =>
      request<CreativesResponse>(`/management/campaigns/${id}/creatives`),
    // 캠페인 삭제 — 내 대시보드에서 삭제 = Meta에서도 삭제(LIVE 모드). 자식 광고세트·광고 함께.
    deleteCampaign: (id: string) =>
      request<{ result: { status: string; failure_reason?: string | null } }>(
        `/management/campaigns/${id}`,
        { method: "DELETE" },
      ),
    // 수동 KPI(추정 CVR·ROAS) — 조직 단위 DB 영속
    kpiOverrides: () =>
      request<{ overrides: ManualKpiMap }>(`/management/kpi-overrides`),
    putKpiOverride: (id: string, body: { cvr: number | null; roas: number | null }) =>
      request<{ campaign_id: string; cvr: number | null; roas: number | null }>(
        `/management/campaigns/${id}/kpi-override`,
        { method: "PUT", body: JSON.stringify(body) },
      ),
    createCampaignProposal: (body: {
      name: string;
      objective?: 'traffic' | 'leads'; // 리드면 잠재고객 폼까지 생성(전환·ROAS 측정용)
      daily_budget_krw: number;
      run_days: number;
      creative_ad_id?: string;
      image_hash?: string; // /ad-image 업로드 결과 — 광고 소재 이미지
      special_ad_category?: string; // NONE | HOUSING | EMPLOYMENT | CREDIT | ISSUES_ELECTIONS_POLITICS
      country?: string; // ISO2 (KR 등)
      age_min?: number;
      age_max?: number;
      gender?: 'all' | 'male' | 'female';
    }) =>
      request<{ proposal: Proposal }>("/management/campaigns/create-proposal", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // generator 후보 → CREATE_CAMPAIGN 제안(시뮬 없는 빠른 집행). 승인·집행은 approve·execute 재사용.
    fromCandidate: (body: {
      generation_id: string;
      candidate_id: string;
      objective?: 'traffic' | 'leads';
      link_url: string;
      name: string;
      daily_budget_krw: number;
      start_date: string; // YYYY-MM-DD (Meta 광고세트 start_time)
      end_date?: string | null; // YYYY-MM-DD (Meta 광고세트 end_time)
      special_ad_category?: string;
      country?: string;
      age_min?: number;
      age_max?: number;
      gender?: 'all' | 'male' | 'female';
    }) =>
      request<{ proposal: Proposal }>("/management/campaign-proposals/from-candidate", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // 시뮬 결과 → CREATE_CAMPAIGN 제안(집행 권장 판정 시에만). 권장 집행 경로.
    fromSimulation: (body: {
      simulation_id: string;
      link_url: string;
      name: string;
      daily_budget_krw: number;
      start_date: string; // YYYY-MM-DD (Meta 광고세트 start_time)
      end_date?: string | null; // YYYY-MM-DD (Meta 광고세트 end_time)
      special_ad_category?: string;
      country?: string;
      age_min?: number;
      age_max?: number;
      gender?: 'all' | 'male' | 'female';
    }) =>
      request<{ proposal: Proposal }>("/management/campaign-proposals/from-simulation", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // 기존 Meta 캠페인 타겟팅 정보 조회 — 시뮬레이터 사전 입력용
    campaignTargeting: (campaignId: string) =>
      request<{
        campaign_id: string;
        campaign_name: string;
        objective: string;
        age_min: number | null;
        age_max: number | null;
        gender: '' | 'M' | 'F';
        ad_headline: string | null;
        ad_body: string | null;
        ad_image_url: string | null;
        category_id: number;
        service_class: number;
        suggested_persona_count: number;
        reach: number; // Meta 실측 도달수(원값) — 표본 상한 200과 별개
      }>(`/management/campaigns/${campaignId}/targeting`),
    // 캠페인 이름 자동 제안 — 소재·시뮬 집계 기반 후보 3개(LLM 실패 시 규칙 폴백)
    nameSuggestions: (simulationId: string) =>
      request<{ names: string[] }>(
        `/management/campaign-proposals/name-suggestions?simulation_id=${encodeURIComponent(simulationId)}`,
      ),
    // 기존 Meta 캠페인에 시뮬 역방향 연결
    linkSimulation: (campaignId: string, simulationId: string) =>
      request<{ campaign_id: string; simulation_id: string; linked: boolean }>(
        `/management/campaigns/${campaignId}/link-simulation`,
        { method: 'POST', body: JSON.stringify({ simulation_id: simulationId }) },
      ),
    // 광고 소재 이미지 업로드 → image_hash (멀티파트, 무과금 자산 등록)
    uploadAdImage: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return authedFetch(`${API_BASE}/api/management/ad-image`, { method: 'POST', body: form }).then(
        (r) => r.json() as Promise<{ image_hash: string }>,
      );
    },
    // 샘플 시안 — FB 피드·인스타 미리보기 HTML(Meta iframe)
    adPreview: (imageHash: string, name?: string) =>
      request<{ previews: { format: string; html: string }[] }>("/management/ad-preview", {
        method: "POST",
        body: JSON.stringify({ image_hash: imageHash, name }),
      }),
    budget: () => request<BudgetStatus>("/management/budget"),
    setBudgetLimit: (limitKrw: number) =>
      request<BudgetStatus>("/management/budget/limit", {
        method: "POST",
        body: JSON.stringify({ limit_krw: limitKrw }),
      }),
    // 게재 시작(활성화) — 크레딧 잔액 게이트 → spend_cap → 캠페인·세트·광고 ACTIVE
    activate: (campaignId: string, commitKrw?: number) =>
      request<ActivateResponse>(`/management/campaigns/${campaignId}/activate`, {
        method: "POST",
        body: JSON.stringify({ commit_krw: commitKrw }),
      }),
    // 게재 여부 + 불가 원인 + 크레딧 잔액
    deliveryStatus: (campaignId: string) =>
      request<DeliveryStatusResponse>(`/management/campaigns/${campaignId}/delivery-status`),
    // Meta 소진액 → 크레딧 차감 정산 + 자동 종료 반영
    syncCampaign: (campaignId: string) =>
      request<SyncResponse>(`/management/campaigns/${campaignId}/sync`),
    // 캠페인 즉시 일시중지(PAUSED) — 게재·과금 중단
    pause: (campaignId: string) =>
      request<PauseResponse>(`/management/campaigns/${campaignId}/pause`, { method: 'POST' }),
    // 이 캠페인으로 제출된 잠재고객(리드) 명단 — Meta leadgen 조회(권한 필요 시 note)
    leads: (campaignId: string) =>
      request<LeadsResponse>(`/management/campaigns/${campaignId}/leads`),
    // 운영 알림(이상 감지 C안) — 스펙 2026-07-03 §2
    notifications: {
      list: (params?: { project_id?: string; unread_only?: boolean }) => {
        const q = new URLSearchParams();
        if (params?.project_id) q.set("project_id", params.project_id);
        if (params?.unread_only) q.set("unread_only", "true");
        const qs = q.toString();
        return request<{ notifications: ManagementNotification[]; unread_count: number }>(
          `/management/notifications${qs ? `?${qs}` : ""}`,
        );
      },
      read: (ids: string[]) =>
        request<{ updated: number }>(`/management/notifications/read`, {
          method: "POST",
          body: JSON.stringify({ ids }),
        }),
      resolve: (id: string, resolution: "ignored" | "actioned") =>
        request<{ resolved: boolean; resolution: "ignored" | "actioned" }>(
          `/management/notifications/${id}/resolve`,
          { method: "POST", body: JSON.stringify({ resolution }) },
        ),
      consult: (id: string) =>
        request<
          | { status: "consult"; session_id: string }
          | { status: "normal"; message: string }
          | { status: "already_resolved"; resolution: string }
        >(`/management/notifications/${id}/consult`, { method: "POST" }),
      // 수동 이상 점검 — 스캔 즉시 실행. 잠금 409·쿨다운 429는 ApiError.message(detail)로 노출.
      notifyScan: () =>
        request<{
          scanned_findings: number;
          delivered: number;
          skipped: { campaign_id: string; reason: string }[];
          failed: { campaign_id: string; reason: string }[];
        }>(`/management/anomaly/notify-scan`, { method: "POST" }),
    },
  },

  generator: {
    start: (body: object) =>
      request("/generator/generations", { method: "POST", body: JSON.stringify(body) }),
    stream: (generationId: string) =>
      new EventSource(`${API_BASE}/api/generator/generations/${generationId}/stream`, {
        withCredentials: true,
      }),
    detail: (generationId: string) => request(`/generator/generations/${generationId}`),
    select: (generationId: string, candidateId: string) =>
      request(`/generator/generations/${generationId}/select`, {
        method: "POST",
        body: JSON.stringify({ candidate_id: candidateId }),
      }),
    publish: (generationId: string, candidateId: string, caption: string) =>
      request(`/generator/generations/${generationId}/publish`, {
        method: "POST",
        body: JSON.stringify({ candidate_id: candidateId, caption }),
      }),
    list: (limit = 20) => request(`/generator/generations?limit=${limit}`),
    brandProfile: {
      get: (clientId: string) =>
        request<{
          brand_color: string | null;
          brand_logo_key: string | null;
          brand_logo_url: string | null;
          tone_and_manner: string | null;
        }>("/generator/brand-profile", { headers: { "X-Client-Id": clientId } }).then((p) => ({
          ...p,
          brand_logo_url: p.brand_logo_url ? `${API_BASE}${p.brand_logo_url}` : null,
        })),
      save: (
        clientId: string,
        body: { brand_color?: string | null; brand_logo_key?: string | null; tone_and_manner?: string | null },
      ) =>
        request("/generator/brand-profile", {
          method: "POST",
          headers: { "X-Client-Id": clientId },
          body: JSON.stringify(body),
        }),
      uploadLogo: async (clientId: string, file: File): Promise<{ key: string; url: string }> => {
        const form = new FormData();
        form.append("file", file);
        const res = await authedFetch(`${API_BASE}/api/generator/logo`, {
          method: "POST",
          headers: { "X-Client-Id": clientId },
          body: form,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Unknown error" }));
          throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
        }
        const data = (await res.json()) as { key: string; url: string };
        return { ...data, url: `${API_BASE}${data.url}` };
      },
    },
    brandKits: {
      list: () => request<{ kits: BrandKit[] }>("/generator/brand-kits"),
      create: (body: BrandKitInput) =>
        request<BrandKit>("/generator/brand-kits", {
          method: "POST",
          body: JSON.stringify(body),
        }),
      update: (id: string, body: BrandKitInput) =>
        request<BrandKit>(`/generator/brand-kits/${id}`, {
          method: "PUT",
          body: JSON.stringify(body),
        }),
      remove: (id: string) =>
        request(`/generator/brand-kits/${id}`, { method: "DELETE" }),
    },
    uploadProductImage: async (file: File): Promise<{ temp_key: string }> => {
      const form = new FormData();
      form.append("file", file);
      const res = await authedFetch(`${API_BASE}/api/generator/product-image`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      return res.json() as Promise<{ temp_key: string }>;
    },
  },

  automation: {
    // 워커(APScheduler)가 서버에서 자동으로 남긴 결과 조회 — 탭 안 열려도 서버 결과를 읽는다.
    runs: (params?: {
      projectId?: string;
      domain?: string;
      unresolved?: boolean;
      limit?: number;
    }) => {
      const q = new URLSearchParams();
      if (params?.projectId) q.set("project_id", params.projectId);
      if (params?.domain) q.set("domain", params.domain);
      if (params?.unresolved) q.set("unresolved", "true");
      if (params?.limit) q.set("limit", String(params.limit));
      const qs = q.toString();
      return request<{ runs: AutomationRunItem[]; count: number }>(
        `/automation/runs${qs ? `?${qs}` : ""}`,
      );
    },
  },
};
