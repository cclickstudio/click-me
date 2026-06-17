// 매니지먼트 API 응답 타입 — 백엔드 contracts/schemas.py 대응

export type Snapshot = { as_of: string; impressions: number; spend_krw: number };

export type Diagnosis = {
  diagnosis_id: string;
  tenant_id: string;
  campaign_id: string;
  anomaly_type: string;
  source: "deterministic" | "agent";
  hypothesis: string;
  confidence: number;
  evidence_metrics: Record<string, unknown>;
  metrics_as_of: string;
  status: string;
};

export type Candidate = { candidate_id: string; sim_score: number | null; preview_url: string | null };

export type Proposal = {
  proposal_id: string;
  tenant_id: string;
  action_type: string;
  action_tier: number;
  evidence_metrics: { candidates?: Candidate[]; selected_candidate_id?: string } & Record<string, unknown>;
  budget_before_krw: number;
  budget_after_krw: number;
  max_total_spend_krw: number;
  expires_at: string;
  proposal_hash: string;
  confidence: number;
  status: string;
};

export type RunResult = {
  fault: string;
  expected: number[];
  snapshots: Snapshot[];
  anomaly_hours: number[];
  diagnosis: Diagnosis | null;
  proposal: Proposal | null;
  relabeled: boolean;
  requires_human: boolean;
  validation_issues: string[];
};

export type ApprovedAction = { approval_id: string; action_tier: number; [k: string]: unknown };
export type ActionResult = {
  result_id: string;
  approval_id: string;
  status: string;
  failure_reason: string | null;
  idempotency_key: string;
};
export type AuditEvent = { event_id: string; category: string; occurred_at: string; payload: Record<string, unknown> };

export type ViewMode = "user" | "arch";
