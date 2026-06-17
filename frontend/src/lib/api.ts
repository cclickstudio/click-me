import { getToken } from "./authApi";
import type { DebateResult, DebateStartResult, SimRunInput, SimRunResult } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

  // 도메인 시뮬레이션(DDD) — /api/simulation/run 동기 실행(multipart/form-data).
  simulation: {
    run: (input: SimRunInput): Promise<SimRunResult> => {
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

      const token = getToken();
      // Content-Type은 지정하지 않는다 — 브라우저가 multipart boundary를 자동 설정.
      return fetch(`${API_BASE}/api/simulation/run`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      }).then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
          throw new Error(err.detail ?? `HTTP ${r.status}`);
        }
        return r.json();
      });
    },
  },

  // 페르소나 토론(/api/debate/*) — 시뮬 반응(reactions)을 받아 토론을 돌리고 결과를 낸다.
  debate: {
    // 시뮬 반응으로 토론 시작 → run_id. 토론은 항상 실 LLM, lay_count는 일반인 수(2|4).
    start: (
      body: {
        reactions: unknown[];
        ad_analysis?: unknown;
        personas?: unknown[];
        simulation_id?: string;
      },
      opts?: { layCount?: 2 | 4 },
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
