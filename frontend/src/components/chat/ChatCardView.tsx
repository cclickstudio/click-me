// 범용 카드 렌더러 — 레지스트리로 섹션 위임. 미등록 kind는 스킵(전방호환) + dev 로그.
'use client';
import { useState, type ReactNode } from 'react';
import type { CardSection, ChatCard, Tone } from '@/lib/chatCard';
import { SECTION_RENDERERS } from './sections';
import ProposalActions from './ProposalActions';

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-[#F2F4F6] text-[#4E5968] dark:bg-[#2D3748] dark:text-[#9CA3AF]',
  muted: 'bg-[#F9FAFB] text-[#8B95A1] dark:bg-[#1C2333] dark:text-[#6B7280]',
  success: 'bg-[#E7F4EC] text-[#15803D] dark:bg-[#14321F] dark:text-[#86EFAC]',
  warning: 'bg-[#FEF3C7] text-[#B45309] dark:bg-[#3B2F0B] dark:text-[#FCD34D]',
  critical: 'bg-[#FEE2E2] text-[#B91C1C] dark:bg-[#3B1212] dark:text-[#FCA5A5]',
};

const STATUS_DOT: Record<string, string> = {
  critical: 'bg-[#E5484D]',
  warning: 'bg-[#F5A623]',
};

function renderSection(section: CardSection): ReactNode {
  const renderer = SECTION_RENDERERS[section.kind] as ((s: CardSection) => ReactNode) | undefined;
  if (!renderer) {
    // 미등록 섹션 kind — 렌더 스킵(전방호환). dev에서만 로깅.
    if (process.env.NODE_ENV !== 'production') {
      console.debug('[chat] unknown card section kind:', section.kind);
    }
    return null;
  }
  return renderer(section);
}

export default function ChatCardView({ card }: { card: ChatCard }) {
  // 집행 결과 카드로 교체되면(onResult) 그걸 우선 렌더하고 ProposalActions는 숨긴다.
  const [resultCard, setResultCard] = useState<ChatCard | null>(null);
  const shown = resultCard ?? card;
  const isResult = resultCard !== null;
  const hasStatusDot = Boolean(shown.status && STATUS_DOT[shown.status]);
  const hasHeader = Boolean(shown.title) || (shown.badges?.length ?? 0) > 0 || hasStatusDot;
  return (
    <div className="flex flex-col gap-3 px-4 py-3 rounded-xl bg-[#F2F4F6] dark:bg-[#252D3D] max-w-sm">
      {hasHeader && (
        <div className="flex flex-wrap items-center gap-1.5">
          {hasStatusDot && shown.status && (
            <span className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[shown.status]}`} aria-hidden />
          )}
          {shown.title && <span className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">{shown.title}</span>}
          {shown.badges?.map((b, i) => (
            <span key={i} className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${TONE_CLASS[b.tone]}`}>
              {b.label}
            </span>
          ))}
        </div>
      )}
      {shown.sections.map((s, i) => (
        <div key={i}>
          {renderSection(s)}
          {!isResult && s.kind === 'proposal' && s.preview_id && s.campaign_id && (
            <ProposalActions
              previewId={s.preview_id}
              campaignId={s.campaign_id}
              threadId={card.trace?.turn_id}
              shownBudgetAfterKrw={s.budget_after_krw}
              onResult={setResultCard}
            />
          )}
        </div>
      ))}
    </div>
  );
}
