import { getToken } from "./authApi";
import type { BoardResponse } from "@/components/manage/compare/types";
import type { CampaignDetail, CampaignsResponse, CreativesResponse, DemographicsResponse, PlatformsResponse } from "@/components/manage/campaigns/types";
import type { Proposal } from "@/components/manage/types";
import type { BudgetStatus } from "@/components/manage/budget/types";
import type {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeader,
      ...(init?.headers as Record<string, string> | undefined),
    },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
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
    sessions: () => request<{ sessions: unknown[] }>("/chat/sessions"),
    messages: (sessionId: string) => request(`/chat/sessions/${sessionId}/messages`),
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
    list: () => request<{ projects: unknown[] }>("/projects"),
    create: (body: { name: string; description?: string }) =>
      request("/projects", { method: "POST", body: JSON.stringify(body) }),
    get: (id: string) => request(`/projects/${id}`),
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
    // conversionValueKrw(전환 1건 가치) 전달 시 구매 외 전환의 추정 ROAS가 채워진다.
    campaigns: (conversionValueKrw?: number | null) =>
      request<CampaignsResponse>(
        `/management/campaigns${conversionValueKrw ? `?conversion_value_krw=${conversionValueKrw}` : ""}`,
      ),
    campaign: (id: string, conversionValueKrw?: number | null) =>
      request<CampaignDetail>(
        `/management/campaigns/${id}${conversionValueKrw ? `?conversion_value_krw=${conversionValueKrw}` : ""}`,
      ),
    campaignPlatforms: (id: string) =>
      request<PlatformsResponse>(`/management/campaigns/${id}/platforms`),
    campaignDemographics: (id: string) =>
      request<DemographicsResponse>(`/management/campaigns/${id}/demographics`),
    campaignCreatives: (id: string) =>
      request<CreativesResponse>(`/management/campaigns/${id}/creatives`),
    createCampaignProposal: (body: {
      name: string;
      daily_budget_krw: number;
      run_days: number;
      creative_ad_id?: string;
    }) =>
      request<{ proposal: Proposal }>("/management/campaigns/create-proposal", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    budget: () => request<BudgetStatus>("/management/budget"),
    setBudgetLimit: (limitKrw: number) =>
      request<BudgetStatus>("/management/budget/limit", {
        method: "POST",
        body: JSON.stringify({ limit_krw: limitKrw }),
      }),
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
    advertise: (
      generationId: string,
      body: {
        candidate_id: string;
        budget: number;
        objective: string;
        targeting: { age_min: number; age_max: number; genders: number[]; countries: string[] };
        destination_url: string;
        start_date: string;
        end_date?: string | null;
      },
    ) =>
      request(`/generator/generations/${generationId}/advertise`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    brandProfile: {
      get: (clientId: string) =>
        request<{
          brand_color: string | null;
          brand_logo_key: string | null;
          brand_logo_url: string | null;
          tone_and_manner: string | null;
        }>("/generator/brand-profile", { headers: { "X-Client-Id": clientId } }),
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
        return res.json() as Promise<{ key: string; url: string }>;
      },
    },
  },
};
