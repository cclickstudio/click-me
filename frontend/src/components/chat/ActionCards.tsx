'use client';

// Deep Agent·매니지먼트 추천 조치 카드 — 행동 제안(RESULT)·정책 검토(REVIEW)·액션바(ACTIONBAR)를 렌더.
// 인용(EVIDENCE)은 CitationChips가 담당하므로 여기선 제외한다. 실행(mutating)은 Plan 2까지 비활성.

type CardData = Record<string, unknown>;
type Card = {
  kind: string; // evidence | result | review | actionbar
  status?: string;
  payload: { type: string; version?: number; data: CardData };
};

type ActionItem = {
  id: string;
  label: string;
  kind?: string; // safe | mutating
  enabled?: boolean;
  wired?: boolean;
  disabled_reason?: string;
};

const ACTION_LABELS: Record<string, string> = {
  PAUSE_CAMPAIGN: '캠페인 일시중지',
  ACTIVATE_CAMPAIGN: '캠페인 재개',
  INCREASE_BUDGET: '예산 증액',
  DECREASE_BUDGET: '예산 감액',
};

function actionLabel(type: unknown): string {
  const t = String(type ?? '');
  return ACTION_LABELS[t] ?? t;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

function ResultCard({ data }: { data: CardData }) {
  return (
    <div className='rounded-xl border border-line bg-white dark:bg-[#1A1F2B] px-4 py-3'>
      <div className='flex items-center gap-1.5 mb-1.5'>
        <span className='text-xs font-bold text-ink dark:text-[#E5E8EB]'>
          추천 조치
        </span>
        <span className='rounded-full bg-surface-1 px-1.5 py-0.5 text-[10px] text-ink-tertiary'>
          초안
        </span>
        {data.tier ? (
          <span className='rounded-full bg-surface-1 px-1.5 py-0.5 text-[10px] text-ink-tertiary'>
            {str(data.tier)}
          </span>
        ) : null}
      </div>
      <p className='text-sm font-semibold text-primary mb-1'>
        {actionLabel(data.action_type)}
        {data.target_campaign_id ? (
          <span className='ml-1 text-[11px] font-normal text-ink-tertiary'>
            · {str(data.target_campaign_id)}
          </span>
        ) : null}
      </p>
      {data.rationale ? (
        <p className='text-xs leading-relaxed text-ink-secondary'>
          {str(data.rationale)}
        </p>
      ) : null}
    </div>
  );
}

function ReviewCard({ data }: { data: CardData }) {
  const needsApproval = data.decision === 'needs_approval';
  const reasons = Array.isArray(data.reasons) ? (data.reasons as unknown[]) : [];
  return (
    <div className='rounded-xl border border-line bg-[#F9FAFB] dark:bg-[#161B26] px-4 py-3'>
      <div className='flex items-center gap-1.5 mb-1.5'>
        <span className='text-xs font-bold text-ink dark:text-[#E5E8EB]'>
          정책 검토
        </span>
        <span
          className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
            needsApproval
              ? 'bg-[#FFF4E6] text-[#E8830C] dark:bg-[#3A2A14] dark:text-[#F5A623]'
              : 'bg-[#EAFBF1] text-[#15803D] dark:bg-[#0F2A1C] dark:text-[#4ADE80]'
          }`}>
          {needsApproval ? '승인 필요' : '자동 가능'}
        </span>
      </div>
      {reasons.length > 0 ? (
        <ul className='space-y-0.5'>
          {reasons.map((r, i) => (
            <li key={i} className='text-xs text-ink-secondary'>
              · {str(r)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ActionBar({
  data,
  onAction,
}: {
  data: CardData;
  onAction?: (id: string) => void;
}) {
  const actions = Array.isArray(data.actions)
    ? (data.actions as ActionItem[])
    : [];
  if (actions.length === 0) return null;
  return (
    <div className='flex flex-wrap gap-2'>
      {actions.map(a => {
        const enabled = !!a.enabled;
        return (
          <button
            key={a.id}
            type='button'
            disabled={!enabled}
            title={!enabled ? a.disabled_reason : undefined}
            onClick={enabled ? () => onAction?.(a.id) : undefined}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              a.kind === 'mutating'
                ? 'bg-primary text-primary-foreground hover:bg-primary-hover disabled:bg-[#E5E8EB] disabled:text-ink-muted dark:disabled:bg-[#2D3748] dark:disabled:text-ink-tertiary'
                : 'border border-line text-ink-secondary hover:bg-accent disabled:opacity-40'
            } disabled:cursor-not-allowed`}>
            {a.label}
          </button>
        );
      })}
    </div>
  );
}

export default function ActionCards({
  cards,
  onAction,
}: {
  cards: Card[];
  onAction?: (id: string) => void;
}) {
  // 인용(evidence)은 CitationChips가 담당 — 중복 렌더 방지.
  const visible = (cards ?? []).filter(c => c.kind !== 'evidence');
  if (visible.length === 0) return null;
  return (
    <div className='mt-1.5 w-full space-y-2'>
      {visible.map((c, i) => {
        if (c.kind === 'result') return <ResultCard key={i} data={c.payload.data} />;
        if (c.kind === 'review') return <ReviewCard key={i} data={c.payload.data} />;
        if (c.kind === 'actionbar')
          return <ActionBar key={i} data={c.payload.data} onAction={onAction} />;
        return null;
      })}
    </div>
  );
}

export type { Card as ActionCard };
