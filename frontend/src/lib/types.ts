export type UserRole = "admin" | "user";

export interface OCEAN {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  neuroticism: number;
}

export interface PersonaAttributes {
  age: number;
  gender: string;
  region: string;
  occupation: string;
  income_level: string;
  education: string;
  purchase_motivation: string;
  price_sensitivity: number;
  brand_loyalty: number;
  trigger_words: string[];
  rejection_words: string[];
  current_emotion: string;
}

export interface Persona {
  persona_id: string;
  segment: string;
  ocean: OCEAN;
  attributes: PersonaAttributes;
  temperature: number;
  seed: number;
}

/* ─── Simulation (domain /api/simulation/run 계약) ─── */

export interface SimAisas {
  attention: boolean;
  interest: boolean;
  search: boolean;
  action: boolean;
  share: boolean;
}

export interface SimPersonaReaction {
  persona_id: string;
  exposure_context: string | null;
  weight: number;
  aisas: SimAisas;
  drop_stage: string | null;
  drop_reason_tag: string | null;
  purchase_intent: number;
  trust: number;
  rejected: boolean;
  rejection_reason_tag: string | null;
  emotion_tag: string;
  perceived_message: string | null;
  perceived_target: string | null;
  utterance: string | null;
  qa_passed: boolean;
  qa_fail_reason: string | null;
}

export interface SimRubricScore {
  dimension: string;
  score: number;
  evidence: Record<string, unknown>;
}

export interface SimAggregate {
  click_intent_rate: number;
  ci_low: number;
  ci_high: number;
  purchase_intent: number;
  trust_avg: number;
  rejection_rate: number;
  variance_warning: boolean;
  effective_n: number;
  payload: Record<string, unknown>;
  engine_version: string;
}

export interface SimAdAnalysis {
  ad_id: string;
  structured_analysis: Record<string, unknown>;
  detected_industry: string | null;
  detected_objective: string | null;
  detected_target: string | null;
  detected_message: string | null;
  ad_features: Record<string, unknown>;
  intent_mismatch: boolean;
  mismatch_detail: Record<string, unknown> | null;
  model_version: string;
}

export interface SimPersona {
  persona_id: string;
  age: number;
  gender: string;
  region: string;
  ocean: Record<string, number>;
  media_behavior: Record<string, unknown>;
  consumption_values: Record<string, unknown>;
  socioeconomic: Record<string, unknown>;
  weight: number;
  profile_narrative: string;
}

export interface SimRunResult {
  run_id: string;
  ad_analysis: SimAdAnalysis | null;
  personas: SimPersona[];
  reactions: SimPersonaReaction[];
  rubric_scores: SimRubricScore[];
  aggregate: SimAggregate | null;
  simulation_id?: string;
}

export interface SimCategoryKind {
  id: number; // NICE 상품분류 류 번호 (= service_class)
  description: string;
}

export interface SimCategory {
  id: number;
  name: string; // 업종 대분류명 (= product_category)
  kinds: SimCategoryKind[];
}

export interface SimRunInput {
  ad_id: string;
  ad_content?: string;
  ad_image?: File | null;
  ad_image_url?: string;
  organization_id?: string;
  project_id?: string;
  target_filter?: Record<string, unknown>;
  target_mode?: "AUTO" | "MANUAL";
  sample_size?: number;
  allocation?: "proportional" | "stratified";
  ad_title?: string;
  product_category?: string;
  ad_objective?: string;
  service_class?: number;
}

/* ─── Debate (페르소나 토론 /api/debate/*) ─── */

export type DebateStance = "positive" | "neutral" | "negative";

// 추가 토론용 논제 후보(/api/debate/topics) — ranking 순 정렬, headline을 제목으로 노출.
export interface DebateTopic {
  topic_id: string;
  headline: string;
  diagnosis: string;
  question: string;
  primary_signal: string;
  focus: string;
  objective: string;
  ranking: number;
  confidence: number;
}

export interface DebateTopicsResult {
  topics: DebateTopic[];
}

export interface DebateStartResult {
  run_id: string;
  stream_url: string;
  lay_count: number;
}

/* ─── Debate Q&A (/api/debate/{run_id}/question) — POST SSE ─── */

// 종료 후 Q&A에서 페르소나가 답하는 한 발언.
export interface QAUtteranceEvent {
  event: "progress";
  stage: "qa_utterance";
  persona_id: string;
  persona_name: string;
  role: string;
  engine: string;
  stance: DebateStance;
  text: string;
  reason: string;
  lever: string;
}

// 진행자(주최자) 중간 멘트.
export interface QAModeratorEvent {
  event: "progress";
  stage: "qa_moderator";
  text: string;
}

// Q&A 종료 신호.
export interface QACompletedEvent {
  event: "completed";
  stage: "qa_completed";
}

export interface QAErrorEvent {
  event: "error";
  stage?: string;
  message?: string;
}

export type QAEvent = QAUtteranceEvent | QAModeratorEvent | QACompletedEvent | QAErrorEvent;

export interface DebateUtterance {
  round: number;
  phase: string; // 발산 / 반박 / 검증
  stance: DebateStance;
  text: string;
  reason: string;
  lever: string;
}

export interface DebateParticipantDebate {
  persona_id: string;
  persona_name: string;
  persona_profile: string;
  role: string;
  engine: string;
  utterances: DebateUtterance[];
}

export interface RankedAction {
  rank: number;
  action: string;
  expected_effect: string;
  supporting_personas: string[];
}

export interface JudgeFinal {
  headline: string; // 전문가용 진단
  plain_summary: string; // 비전문가용 쉬운 결론
  consensus: string[];
  dissent: string[];
  ranked_actions: RankedAction[];
}

export interface DebateData {
  topic: string;
  rounds_run: number;
  stop_reason: string; // consensus / dissensus / max
  models: { judge?: string; engines?: string[] };
  participants: DebateParticipantDebate[];
  round_summaries: Record<string, string>;
  proposed_actions: string[];
  final: JudgeFinal | null;
}

export interface DebateReportQuote {
  persona_name: string;
  role: string;
  stance: DebateStance;
  text: string;
}

export interface DebateReport {
  headline: string; // 전문가용
  plain_summary: string; // 비전문가용
  topic: string;
  debate_available: boolean;
  rounds_run: number;
  stop_reason: string | null;
  consensus: string[];
  dissent: string[];
  ranked_actions: RankedAction[];
  quotes: DebateReportQuote[];
  consumer_groups: Record<string, number>;
}

export interface DebateResult {
  run_id: string;
  simulation_id: string | null;
  debate_id: string | null;
  topic: { headline: string; diagnosis: string; question: string; primary_signal: string };
  debate: DebateData | null;
  report: DebateReport;
}

// SSE 토론 진행 이벤트(stage에 따라 채워지는 필드가 다름).
export interface DebateSSEEvent {
  event: "progress" | "completed" | "error";
  stage?: string; // analysis/kpi/topic/selection/assignment/utterance/round_summary/judge_final/report
  pct?: number;
  message?: string;
  // utterance stage
  round?: number;
  phase?: string;
  persona_id?: string;
  persona_name?: string;
  persona_profile?: string;
  role?: string;
  engine?: string;
  stance?: DebateStance;
  text?: string;
  reason?: string;
  lever?: string;
  // round_summary stage
  summary?: string;
  // judge_final stage
  rounds_run?: number;
  stop_reason?: string;
  headline?: string;
}

export interface SSEProgressEvent {
  event: "progress" | "milestone" | "completed" | "error";
  stage?: string;
  pct?: number;
  message?: string;
  result_url?: string;
}

export interface AdAnalysis {
  ad_id: string;
  confidence: number;
  text_analysis: {
    headline: string | null;
    sub_headline: string | null;
    body: string | null;
    cta: string | null;
    usp_extracted: string[];
    emotional_keywords: string[];
  };
  visual_analysis: {
    dominant_colors: string[];
    emotional_tone: string | null;
    layout_type: string | null;
    brand_elements: string[];
  } | null;
  strategic_analysis: {
    target_demographic: string | null;
    purchase_stage_target: "awareness" | "consideration" | "conversion";
    usp: string | null;
    key_message: string | null;
    likely_resonates_with: string[];
    likely_resists_with: string[];
    potential_objections: string[];
  };
}

export interface ChatMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
  last_message_at: string;
  message_count: number;
}

export interface Inquiry {
  inquiry_id: string;
  title: string;
  content: string;
  contact_email: string | null;
  created_at: string;
}

export interface User {
  user_id: string;
  login_id: string;
  name: string;
  role: UserRole;
  created_at: string;
  last_login_at: string | null;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: "active" | "archived";
  created_at: string;
}

/* ─── Generator ─── */

export interface GeneratorCopy {
  headline: string;
  body: string;
  cta: string;
}

export interface QualityCheckItem {
  passed: boolean;
  score: number;
  feedback: string;
}

export interface QualityReport {
  typo_check: QualityCheckItem;
  duplicate_check: QualityCheckItem;
  cta_exists: QualityCheckItem;
  readability: QualityCheckItem;
  target_fit: QualityCheckItem;
  text_length: QualityCheckItem;
  brand_consistency: QualityCheckItem;
  overall_passed: boolean;
}

export interface GeneratorCandidate {
  candidate_id: string;
  idx: number;
  strategy: {
    strategy_type: string;
    strategy_description?: string;
    rationale?: string;
  };
  template_id: string;
  copy: GeneratorCopy;
  s3_key: string;
  image_url: string | null;
  qa_result: QualityReport | null;
  qa_passed: boolean | null;
  explanation: {
    applied_target: string;
    applied_strategy: string;
    applied_template: string;
    rationale: string;
  } | null;
}

export interface GenerationPublishLog {
  id: string;
  candidate_id: string | null;
  platform: string;
  status: string;
  ig_media_id: string | null;
  caption: string | null;
  error_message: string | null;
  created_at: string;
}

export interface GenerationDetail {
  generation_id: string;
  status: "pending" | "running" | "completed" | "failed";
  input: Record<string, unknown>;
  strategies: unknown[] | null;
  selected_candidate_id: string | null;
  error_message: string | null;
  created_at: string;
  candidates: GeneratorCandidate[];
  publish_logs: GenerationPublishLog[];
}

export interface CampaignResult {
  generation_id: string;
  candidate_id: string;
  status: "created" | "failed" | "mocked";
  success: boolean;
  mocked: boolean;
  campaign_id: string | null;
  adset_id: string | null;
  creative_id: string | null;
  ad_id: string | null;
  error: string | null;
  ads_manager_url: string | null;
}

export interface PublishResult {
  generation_id: string;
  candidate_id: string;
  status: "published" | "failed" | "mocked";
  success: boolean;
  mocked: boolean;
  media_id: string | null;
  error: string | null;
}
