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

export interface ScoreDistribution {
  mean: number;
  std: number;
  p10: number;
  p90: number;
  raw_probs: number[];
}

export interface SimulationResult {
  simulation_id: string;
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  p0: {
    persona_reactions: Array<{
      persona_id: string;
      free_text_reaction: string;
      purchase_intent_distribution: number[];
    }>;
    aggregate_purchase_intent: number[];
    kobaco_comparable: boolean;
  };
  p1: {
    signal_distributions: Record<string, ScoreDistribution>;
    kpi: { ctr: number; cvr: number; net_sentiment: number };
    funnel: { attention: number; comprehension: number; click: number; conversion: number };
    langsmith_trace_url: string | null;
    note: string;
  };
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
  email: string;
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
