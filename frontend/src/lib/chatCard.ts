// 채팅 카드 공유 타입 — 백엔드 ChatCard 계약과 1:1. 프론트는 섹션 kind만 보고 렌더한다.
export type Tone = 'neutral' | 'muted' | 'success' | 'warning' | 'critical';
export type CardStatus = 'ok' | 'warning' | 'critical' | 'neutral';

export type Badge = { label: string; tone: Tone };
export type MetricItem = { label: string; value: string; hint?: string };
export type KeyValueItem = { key: string; value: string };
export type Citation = { kind: string; source: string; title?: string };
export type TraceInfo = { turn_id?: string; raw?: Record<string, unknown> };

export type CardSection =
  | { kind: 'summary'; title?: string; text: string }
  | { kind: 'metrics'; title?: string; items: MetricItem[] }
  | { kind: 'entity'; title?: string; items: KeyValueItem[] }
  | { kind: 'proposal'; title?: string; action_type: string; rationale?: string; proposal_id?: string;
      preview_id?: string; tier?: string; budget_before_krw?: number; budget_after_krw?: number; executable?: boolean }
  | { kind: 'review'; title?: string; decision: string; rationale?: string }
  | { kind: 'diagnosis'; title?: string; anomaly_type: string; status: string; confidence: number; hypothesis?: string }
  | { kind: 'evidence'; title?: string; citations?: Citation[]; used_tools?: string[] }
  | { kind: 'empty_state'; title?: string; text: string };

export type ChatCard = {
  version: 1;
  type: 'management' | 'report' | 'qa' | 'generic';
  title?: string;
  status?: CardStatus;
  badges?: Badge[];
  sections: CardSection[];
  trace?: TraceInfo;
};

// SSE 이벤트(카드 프로토콜) — data.kind로 분기.
export type CardEvent =
  | { kind: 'summary_delta'; text: string }
  | { kind: 'card'; payload: ChatCard }
  | { kind: 'final'; turn_id?: string; status: 'ok' | 'partial' | 'failed' }
  | { kind: 'error'; scope?: string; message: string };

const CARD_EVENT_KINDS = new Set(['summary_delta', 'card', 'final', 'error']);

export function isCardEvent(data: unknown): data is CardEvent {
  if (typeof data !== 'object' || data === null || !('kind' in data)) return false;
  const kind = (data as { kind: unknown }).kind;
  return typeof kind === 'string' && CARD_EVENT_KINDS.has(kind);
}
