import { getToken } from "./authApi";
import type { BoardResponse } from "@/components/manage/compare/types";
import type { CampaignDetail, CampaignsResponse } from "@/components/manage/campaigns/types";
import type { Proposal } from "@/components/manage/types";

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

  simulate: {
    start: (body: object) => request("/simulate/reactions", { method: "POST", body: JSON.stringify(body) }),
    result: (taskId: string) => request(`/simulate/${taskId}/result`),
    stream: (taskId: string) => new EventSource(`${API_BASE}/api/simulate/${taskId}/stream`),
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
    compareBoard: () => request<BoardResponse>("/management/compare/board"),
    campaigns: () => request<CampaignsResponse>("/management/campaigns"),
    campaign: (id: string) => request<CampaignDetail>(`/management/campaigns/${id}`),
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
