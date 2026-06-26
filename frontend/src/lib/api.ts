import { getToken } from "./authApi";
import type { BoardResponse } from "@/components/manage/compare/types";
import type { CampaignDetail, CampaignsResponse, CreativesResponse, DemographicsResponse, ManualKpiMap, PlatformsResponse } from "@/components/manage/campaigns/types";
import type { Proposal } from "@/components/manage/types";
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
  SimRunInput,
  SimRunResult,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  prediction: PredictionSnapshot | null;
  actual: ActualOutcome;
  verdict: 'aligned' | 'overperformed' | 'underperformed' | 'unknown';
  rationale: string;
  interpretation?: string; // 보조 KPI 기반 결정론 해석 — 없으면 빈 문자열
}
export interface BeforeAfterResponse {
  items: BeforeAfterItem[];
  rate_limited?: string; // Meta 요청 한도 시 안내
}

// FastAPI 에러 detail 정규화 — 422는 detail이 배열({loc,msg,type})이라 그대로 두면 "[object Object]"로 깨진다.
function errDetail(err: unknown, status: number): string {
  const d = (err as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    const msgs = d
      .map((e) =>
        e && typeof e === "object" && "msg" in e
          ? String((e as { msg: unknown }).msg)
          : null,
      )
      .filter(Boolean) as string[];
    if (msgs.length) return msgs.join(", ");
  }
  return `HTTP ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const { headers: initHeaders, ...restInit } = init ?? {};
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeader,
      ...(initHeaders as Record<string, string> | undefined),
    },
    ...restInit,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(errDetail(err, res.status));
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
  return form;
}

// 캠페인 조회 쿼리스트링 — 전환가치·목표 ROAS는 입력됐을 때만 붙인다.
// 조회 기간 토글 — 전체 누적(maximum) / 최근 30일 / 이번 달. Ads Manager와 맞추기용.
export type DatePreset = "maximum" | "last_30d" | "this_month";

function _campaignQuery(
  conversionValueKrw?: number | null,
  targetRoas?: number | null,
  datePreset?: DatePreset,
): string {
  const p = new URLSearchParams();
  if (conversionValueKrw) p.set("conversion_value_krw", String(conversionValueKrw));
  if (targetRoas) p.set("target_roas", String(targetRoas));
  if (datePreset && datePreset !== "maximum") p.set("date_preset", datePreset);
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
export type ChatHistoryMessage = {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  meta?: unknown;
  created_at?: string | null;
};

export const api = {
  ads: {
    upload: (file: File, projectId: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("project_id", projectId);
      return fetch(`${API_BASE}/api/ads/upload`, { method: "POST", body: form }).then((r) => r.json());
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
      const token = getToken();
      // Content-Type은 지정하지 않는다 — 브라우저가 multipart boundary를 자동 설정.
      return fetch(`${API_BASE}/api/simulation/run`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
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
      const token = getToken();
      return fetch(`${API_BASE}/api/simulation`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: buildSimForm(input),
      }).then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
          throw new Error(err.detail ?? `HTTP ${r.status}`);
        }
        return r.json();
      });
    },
    stream: (runId: string) => new EventSource(`${API_BASE}/api/simulation/${runId}/stream`),
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
    stream: (runId: string) => new EventSource(`${API_BASE}/api/debate/${runId}/stream`),
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
      const token = getToken();
      const res = await fetch(
        `${API_BASE}/api/debate/by-simulation/${simulationId}/report`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
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
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/debate/${runId}/question`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
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
    adviceUsage: (projectId: string) =>
      request<{ used: number; limit: number }>(
        `/chat/advice-usage?project_id=${encodeURIComponent(projectId)}`,
      ),
    // 개선 루프(시뮬↔제너) 상태 — 3턴 도달 시 '개선 시안 만들기' 제안을 숨기는 데 쓴다.
    loopState: (sessionId: string) =>
      request<{
        loop_count: number;
        max_loop: number;
        can_improve: boolean;
        phase: string;
      }>(`/chat/loop-state?session_id=${encodeURIComponent(sessionId)}`),
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
      const token = getToken();
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/api/chat/image`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
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

  inquiries: {
    create: (body: { title: string; content: string; contact_email?: string }) =>
      request("/inquiries", { method: "POST", body: JSON.stringify(body) }),
  },

  admin: {
    users: () => request<{ users: unknown[] }>("/admin/users"),
    createUser: (body: object) => request("/admin/users", { method: "POST", body: JSON.stringify(body) }),
    inquiries: () => request<{ inquiries: unknown[] }>("/admin/inquiries"),
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
    approve: (proposal: unknown, approved: boolean) =>
      request("/management/approve", {
        method: "POST",
        body: JSON.stringify({ proposal, approved, approver_id: "user_demo" }),
      }),
    execute: (approved_action: unknown, proposal: unknown) =>
      request("/management/execute", {
        method: "POST",
        body: JSON.stringify({ approved_action, proposal }),
      }),
    audit: (approvalId: string) => request(`/management/audit?approval_id=${approvalId}`),
    // 멀티테넌트 — 로그인 org로 Meta OAuth 로그인 URL을 받는다(인증 XHR). 프론트가 그 URL로 이동.
    connectMeta: () => request<{ login_url: string; state: string }>("/management/meta/connect"),
    compareBoard: () => request<BoardResponse>("/management/compare/board"),
    // 집행 전(시뮬 예측) vs 후(실측) — ClickMe로 만든 캠페인별
    beforeAfter: () => request<BeforeAfterResponse>("/management/compare/before-after"),
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
    ) =>
      request<CampaignsResponse>(
        `/management/campaigns${_campaignQuery(conversionValueKrw, targetRoas, datePreset)}`,
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
    // 광고 소재 이미지 업로드 → image_hash (멀티파트, 무과금 자산 등록)
    uploadAdImage: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return fetch(`${API_BASE}/api/management/ad-image`, { method: 'POST', body: form }).then(
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
  },

  generator: {
    start: (body: object) =>
      request("/generator/generations", { method: "POST", body: JSON.stringify(body) }),
    stream: (generationId: string) =>
      new EventSource(`${API_BASE}/api/generator/generations/${generationId}/stream`),
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
        const res = await fetch(`${API_BASE}/api/generator/logo`, {
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
      const res = await fetch(`${API_BASE}/api/generator/product-image`, {
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
};
