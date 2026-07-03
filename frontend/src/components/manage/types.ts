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
  // 탐지 기준(가정치) — 백엔드 policy.py·exposure_model.py 단일원천(CPM 앵커는 국내 실측)
  assumptions?: {
    daily_budget_krw: number;
    cpm_anchor_krw: number;
    cpm_normal_range_krw: [number, number];
    base_ctr: number;
    deficit_threshold: number; // 기대 대비 이 비율 미만이면 결핍
    min_consecutive_hours: number; // 결핍 연속 최소 시간
    sources: { label: string; url: string }[];
  };
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
  // 생성 결과 스냅샷 — campaign_meta_id(LIVE 생성 시 Meta 캠페인 id) 등.
  platform_response_snapshot?: { campaign_meta_id?: string } & Record<string, unknown>;
};
export type AuditEvent = { event_id: string; category: string; occurred_at: string; payload: Record<string, unknown> };

export type ViewMode = "user" | "arch";

// action_type → 한국어 라벨 (에스컬레이션 사다리 신규 액션 포함). 미등록은 원문 노출.
export const ACTION_LABELS: Record<string, string> = {
  PAUSE_CAMPAIGN: "캠페인 끄기",
  DECREASE_BUDGET: "예산 감액",
  INCREASE_BUDGET: "예산 증액",
  REPLACE_CREATIVE: "소재 교체",
  CREATE_CAMPAIGN: "캠페인 재생성",
  EXPAND_AUDIENCE: "타겟 범위 확장",
  CHANGE_BID_STRATEGY: "입찰 전략 변경",
};

export const actionLabel = (actionType: string): string => ACTION_LABELS[actionType] ?? actionType;
