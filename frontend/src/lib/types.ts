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

export interface ObjectiveContribution {
  label: string;
  value: number; // 0~1 정규화 신호값
  weight: number;
}

export interface ObjectiveFit {
  objective: string;
  matched_goal: string;
  score: number; // 0~100 상대 지수(확률 아님)
  grade: string; // 높음 / 보통 / 낮음
  rationale: string;
  contributions: ObjectiveContribution[];
  low_confidence: boolean;
  exploratory: boolean;
}

export interface OceanBandKpis {
  n: number;
  effective_n: number;
  click_intent_rate: number;
  purchase_intent: number;
  trust_avg: number;
  rejection_rate: number;
}

export interface OceanDimensionSegment {
  dimension: string;
  dimension_ko: string;
  high: OceanBandKpis | null;
  low: OceanBandKpis | null;
  click_gap: number | null; // 높음−낮음 클릭의향 격차(한쪽 밴드 비면 null)
  low_confidence: boolean;
}

export interface OceanTopDriver {
  dimension: string;
  dimension_ko: string;
  direction: string; // "높을수록 반응 높음" 등
  click_gap: number;
}

export interface OceanSegments {
  by_dimension: OceanDimensionSegment[];
  top_driver: OceanTopDriver | null;
}

export interface SimRunResult {
  run_id: string;
  ad_analysis: SimAdAnalysis | null;
  personas: SimPersona[];
  reactions: SimPersonaReaction[];
  rubric_scores: SimRubricScore[];
  aggregate: SimAggregate | null;
  objective_fit?: ObjectiveFit | null;
  // OCEAN 성향별 반응 분해(결과 해석) — 즉시 결과 경로에만 포함(콜드 DB 재로드 시 없음).
  ocean_segments?: OceanSegments | null;
  simulation_id?: string;
  // 업로드된 광고 이미지의 표시용 URL(presigned, ~1h). 텍스트 시뮬·로컬폴백이면 없음.
  ad_asset_url?: string | null;
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
  focus: Record<string, number | string | null>; // 4대 KPI·병목 근거 수치
  objective: string;
  ad_title?: string | null; // 광고 제목(제품명) — 토론자 grounding
  ad_description?: string | null; // 광고 설명 — 토론자 grounding
  ad_interpretation?: Record<string, unknown> | null; // 광고 해석 요약(detected_*)
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
  reason?: string; // 왜 그렇게 말했나(무엇에 대한 동의/반대인지 — 인용 맥락)
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
  report_view?: ReportView | null; // 통합 리포트(완료된 토론 결과에만 포함)
}

/* ─── 통합 ReportView — 화면 '최종 결과' = 리포트 = PDF 공용 단일 소스 ─── */

// 리포트용 4대 KPI(시뮬 집계에서 매핑).
export interface ReportKpi {
  click_intent_rate: number;
  ci_low: number;
  ci_high: number;
  purchase_intent: number;
  trust_avg: number;
  rejection_rate: number;
  brand_recognition_rate: number;
  variance_warning: boolean;
  effective_n: number;
}

export interface FunnelStage {
  stage: string;
  passed: number;
  pass_rate: number;
}

export interface Bottleneck {
  from_stage: string;
  to_stage: string;
  dropped: number;
  drop_rate: number;
}

export interface RejectionBreakdown {
  rejected_count: number;
  rejection_rate: number;
  by_rejection_reason_tag: Record<string, number>;
  distrust_count: number;
}

export interface BrandRecognition {
  recognized_count: number;
  recognition_rate: number;
  unrecognized_count: number;
  perceived_brands: Record<string, number>;
}

// ReportView.report — SimulationReport(DebateReport보다 풍부: KPI·퍼널·분포 포함).
export interface SimulationReport {
  headline: string;
  plain_summary: string;
  topic: string;
  kpi: ReportKpi;
  funnel: FunnelStage[];
  bottleneck: Bottleneck | null;
  purchase_intent_dist: Record<string, number>;
  rejection: RejectionBreakdown | null;
  by_drop_reason_tag: Record<string, number>;
  emotion_dist: Record<string, number>;
  brand_recognition: BrandRecognition | null;
  rubric_scores: SimRubricScore[];
  consumer_groups: Record<string, number>;
  debate_available: boolean;
  rounds_run: number;
  stop_reason: string | null;
  consensus: string[];
  dissent: string[];
  ranked_actions: RankedAction[];
  quotes: DebateReportQuote[];
}

// 연령대×성별 세그먼트 1칸(우리 제품 최대 차별점).
export interface SegmentCell {
  age_band: string;
  gender: string;
  n: number;
  effective_n: number;
  click_intent_rate: number;
  purchase_intent: number;
  trust_avg: number;
  rejection_rate: number;
  attention_pass_rate: number;
  low_confidence: boolean;
}

export interface GroupProfile {
  count: number;
  avg_age: number;
  gender_ratio: Record<string, number>;
  top_emotion: string | null;
}

export interface ContributionBar {
  label: string;
  contribution: number;
  value: number;
  weight: number;
}

export interface ConversionStep {
  from_stage: string;
  to_stage: string;
  conversion: number;
}

export interface SummaryMetrics {
  top2box_purchase: number;
  bottom2box_purchase: number;
  positive_emotion_rate: number;
  negative_emotion_rate: number;
  neutral_emotion_rate: number;
  trust_action_gap: number;
  trust_action_label: string;
  contribution_waterfall: ContributionBar[];
  weakest_signal: string | null;
  weakest_linked_action_rank: number | null;
  funnel_conversion: ConversionStep[];
  target_match_rate: number | null;
  discount_rate: number | null;
}

export interface ConfidenceBadge {
  level: string; // high / medium / low
  ci_width: number;
  effective_n: number;
  total_n: number;
  warnings: string[];
}

export interface MessageReception {
  intended: string | null;
  resistance_rate: number;
  resistance_terms: Record<string, number>;
  resisted_quotes: string[];
}

// 리포트 합산 토론 1건 — 주제 + 대표 인용 + 결론(여러 토론이면 각 토론을 간결히 나열).
export interface DebateDigest {
  debate_id?: string | null;
  topic_headline: string;
  diagnosis?: string;
  rounds_run?: number;
  stop_reason?: string | null;
  consensus: string[];
  dissent: string[];
  ranked_actions: {
    rank: number;
    action: string;
    expected_effect: string;
    supporting_personas: string[];
  }[];
  quotes: {
    persona_name: string;
    role: string;
    stance: string;
    text: string;
    reason?: string;
  }[];
}

export interface ReportView {
  run_id: string;
  simulation_id: string | null;
  debate_id: string | null;
  report: SimulationReport;
  objective_fit: ObjectiveFit | null;
  ad_analysis: SimAdAnalysis | null;
  ad: Record<string, unknown> | null;
  topic: DebateTopic | null;
  segments: SegmentCell[];
  group_profiles: Record<string, GroupProfile>;
  message_reception: MessageReception | null;
  summary_metrics: SummaryMetrics;
  confidence: ConfidenceBadge;
  debate: DebateData | null;
  debates?: DebateDigest[]; // 합산 토론(여러 토론 누적) — 없으면 단일 debate 렌더(하위호환).
  aggregate: SimAggregate;
  analysis: Record<string, unknown>;
  generated_at: string;
  report_view_version: string;
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

/* ─── 저장된 토론 조회(/api/debate/by-simulation/{id}·/{id}/detail) — DB 영속화 복원용 ─── */

// 토론 목록 1건(메타, 발언 제외) — 세션 탭·프로젝트 패널 표시용.
export interface DebateSessionMeta {
  debate_id: string;
  simulation_id: string;
  topic: string | null;
  status: string;
  rounds_run: number | null;
  stop_reason: string | null;
  headline: string | null;
  plain_summary: string | null;
  created_at: string | null;
}

export interface DebateSessionsResult {
  debates: DebateSessionMeta[];
}

// 토론 상세 — 메타 + 참가자 + 라운드순 발언 + judge_log + final(복원용).
export interface DebateSessionUtterance {
  round: number;
  phase: string | null;
  stance: DebateStance | null;
  text: string | null;
  reason: string | null;
  lever: string | null;
  persona_id: string | null;
  persona_name: string | null;
  role: string | null;
  engine: string | null;
}

export interface DebateSessionParticipant {
  persona_id: string;
  persona_name: string | null;
  persona_profile: string | null;
  role: string | null;
  engine: string | null;
}

export interface DebateSessionDetail extends DebateSessionMeta {
  models: { judge?: string | null; engines?: string[] };
  round_summaries: Record<string, string>;
  final: JudgeFinal | null;
  participants: DebateSessionParticipant[];
  utterances: DebateSessionUtterance[];
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

export interface BrandKit {
  id: string;
  name: string;
  brand_color: string | null;
  brand_logo_key: string | null;
  tone_and_manner: string | null;
  created_at: string;
}

export interface BrandKitInput {
  name: string;
  brand_color?: string | null;
  brand_logo_key?: string | null;
  tone_and_manner?: string | null;
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
